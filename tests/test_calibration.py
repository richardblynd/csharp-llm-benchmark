from __future__ import annotations

import io
import json
import math
import tempfile
import threading
import unittest
import urllib.error
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from benchmark import calibration, cli
from benchmark.aggregate_benchmark_results import group_results, parse_summary, render_html, render_markdown
from benchmark.calibration import ProbeMeasurement
from benchmark.config import AppConfig, BenchmarkConfig, CalibrationConfig, OpenCodeConfig, PiConfig, apply_cli_overrides, load_config
from benchmark.scorer import TaskScore, score_benchmark
from benchmark.solution import LlmUsage


def config_for_test():
    return AppConfig(
        benchmark=BenchmarkConfig(
            generation_workers=2,
            calibration=CalibrationConfig(warmup_tokens=16, sample_tokens=32, rounds=2, request_timeout_seconds=5),
        ),
        opencode=OpenCodeConfig(version="test"),
        pi=PiConfig(version="test"),
    )


def measured_result(config, speed=10):
    sample = ProbeMeasurement(32, 32 / speed, 0.1, speed)
    with patch("benchmark.calibration._round", return_value=(sample,) * config.benchmark.generation_workers), redirect_stdout(io.StringIO()):
        return calibration.calibrate(config)


@contextmanager
def streaming_endpoint(workers=2, mode="complete"):
    """Real HTTP/SSE fixture; the server barrier proves simultaneous requests."""
    state = SimpleNamespace(requests=[], peak=0, active=0, lock=threading.Lock(), barrier=threading.Barrier(workers))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with state.lock:
                state.requests.append((self.path, payload, self.headers.get("Authorization")))
                state.active += 1
                state.peak = max(state.peak, state.active)
            try:
                state.barrier.wait(timeout=3)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if mode == "error":
                    events = [{"error": {"message": "provider error"}}]
                else:
                    events = [
                        {"choices": [{"delta": {"reasoning": "thinking"}}]},
                        {"choices": [{"delta": {"content": "public class"}}], "usage": {"completion_tokens": 3}},
                        {"choices": [], "usage": {"completion_tokens": payload["max_tokens"], "prompt_tokens": 9000}},
                    ]
                    if mode == "no_usage":
                        events = [{"choices": [{"delta": {"content": "code"}}]}]
                body = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
                if mode != "truncated":
                    body += "data: [DONE]\n\n"
                # Mark the round finished before releasing clients to start another.
                with state.lock:
                    state.active -= 1
                self.wfile.write(body.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, threading.BrokenBarrierError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class SpeedCalibrationTests(unittest.TestCase):
    def test_real_streams_use_configured_concurrency_and_separate_warmup(self):
        config = config_for_test()
        with streaming_endpoint() as (url, state):
            config = replace(config, llm=replace(config.llm, base_url=url, api_key="test-secret"))
            with redirect_stdout(io.StringIO()):
                result = calibration.calibrate(config)
        self.assertEqual(state.peak, 2)
        self.assertEqual([request[1]["max_tokens"] for request in state.requests], [16, 16, 32, 32, 32, 32])
        self.assertEqual(len({request[1]["messages"][1]["content"] for request in state.requests}), 6)
        self.assertTrue(all(request[0] == "/v1/chat/completions" for request in state.requests))
        self.assertTrue(all(request[1]["stream_options"] == {"include_usage": True} for request in state.requests))
        self.assertTrue(all(request[2] == "Bearer test-secret" for request in state.requests))
        self.assertEqual([sample.output_tokens for sample in result.warmup_samples], [16, 16])
        self.assertEqual([sample.output_tokens for sample in result.samples], [32] * 4)
        self.assertTrue(all(sample.time_to_first_token_seconds is not None for sample in result.samples))
        self.assertEqual(result.tokens_per_second, min(sample.tokens_per_second for sample in result.samples))
        for sample in result.samples:
            self.assertAlmostEqual(sample.tokens_per_second, 32 / sample.elapsed_seconds)

    def test_slowest_measured_request_sets_deadline_not_warmup_or_total_throughput(self):
        config = config_for_test()
        sample = lambda speed: ProbeMeasurement(32, 32 / speed, 0.1, speed)
        with patch("benchmark.calibration._round", side_effect=[
            (sample(0.01), sample(1)), (sample(20), sample(12)), (sample(8), sample(16)),
        ]), redirect_stdout(io.StringIO()):
            result = calibration.calibrate(config)
        self.assertEqual(result.tokens_per_second, 8)
        self.assertEqual(result.timeout_seconds, math.ceil(2 * (65536 / 8 + 120)))
        effective = calibration.apply_calibration(config, result)
        self.assertEqual(effective.pi.timeout_seconds, result.timeout_seconds)
        self.assertEqual(effective.opencode.timeout_seconds, result.timeout_seconds)
        self.assertEqual(config.pi.timeout_seconds, 900)

    def test_slow_models_get_longer_deadlines_and_floor_applies(self):
        settings = CalibrationConfig()
        self.assertGreater(calibration.calculate_timeout(5, settings), calibration.calculate_timeout(50, settings))
        self.assertEqual(calibration.calculate_timeout(1000000, settings), 300)
        for speed in (0, -1, float("nan"), float("inf")):
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                calibration.calculate_timeout(speed, settings)

    def test_missing_usage_truncated_stream_and_provider_errors_fail(self):
        config = config_for_test()
        config = replace(config, benchmark=replace(config.benchmark, generation_workers=1))
        for mode in ("no_usage", "truncated", "error"):
            with self.subTest(mode=mode), streaming_endpoint(workers=1, mode=mode) as (url, _state):
                probe_config = replace(config, llm=replace(config.llm, base_url=url))
                with self.assertRaises(RuntimeError):
                    calibration._round(probe_config, 32)

    def test_http_error_reports_status_without_provider_body_or_credentials(self):
        config = config_for_test()
        error = urllib.error.HTTPError(config.llm.base_url, 500, "Server error", {}, io.BytesIO(b"private provider diagnostics"))
        with patch("benchmark.calibration.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500") as raised:
                calibration._probe(config, 32, threading.Barrier(1))
        self.assertNotIn("private provider diagnostics", str(raised.exception))
        self.assertNotIn(config.llm.api_key, str(raised.exception))

    def test_persistence_excludes_credentials_and_requires_same_inputs(self):
        config = config_for_test()
        config = replace(config, llm=replace(config.llm, api_key="test-secret"))
        result = measured_result(config)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            calibration.save_calibration(path, result)
            self.assertNotIn("test-secret", (path / "calibration.json").read_text())
            self.assertEqual(calibration.load_calibration(path, config), result)
            changes = [
                replace(config, llm=replace(config.llm, model="another-model")),
                replace(config, llm=replace(config.llm, base_url="http://other/v1")),
                replace(config, llm=replace(config.llm, top_p=0.5)),
                replace(config, benchmark=replace(config.benchmark, generation_workers=3)),
                replace(config, benchmark=replace(config.benchmark, calibration=replace(config.benchmark.calibration, token_budget=100000))),
            ]
            for changed in changes:
                with self.assertRaisesRegex(ValueError, "differs"):
                    calibration.load_calibration(path, changed)
            payload = json.loads((path / "calibration.json").read_text())
            payload["timeout_seconds"] = 123
            (path / "calibration.json").write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                calibration.load_calibration(path, config)
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "calibration-enabled false"):
            calibration.load_calibration(Path(directory), config)

    def test_config_validates_calibration_and_cli_preserves_settings(self):
        config = load_config(Path("config.example.yaml"))
        self.assertTrue(config.benchmark.calibration.enabled)
        overridden = apply_cli_overrides(config, calibration_enabled=False, generation_workers=3)
        self.assertFalse(overridden.benchmark.calibration.enabled)
        self.assertEqual(overridden.benchmark.calibration.token_budget, 65536)
        self.assertEqual(overridden.benchmark.generation_workers, 3)
        for entry in ("rounds: 0", "sample_tokens: 0", "request_timeout_seconds: -1", "safety_factor: 0.5", "safety_factor: nan", "overhead_seconds: -1"):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.yaml"
                path.write_text(f'opencode:\n  version: "test"\nbenchmark:\n  calibration:\n    {entry}\n')
                with self.assertRaises(ValueError):
                    load_config(path)


class CalibrationIntegrationTests(unittest.TestCase):
    def test_failed_calibration_stops_before_agent_execution(self):
        args = cli._build_parser().parse_args(["run"])
        with patch("benchmark.cli.load_config", return_value=config_for_test()), patch(
            "benchmark.cli.resolve_model_meta"
        ), patch("benchmark.cli.load_tasks", return_value=[]), patch(
            "benchmark.cli.validate_tasks", return_value=[]
        ), patch("benchmark.cli._report_quantization_precedence"), patch(
            "benchmark.cli.calibrate", side_effect=RuntimeError("No usable speed")
        ), patch("benchmark.cli._execute_benchmark") as execute:
            with self.assertRaisesRegex(RuntimeError, "No usable speed"):
                cli._run(args)
        execute.assert_not_called()

    def test_all_calibrates_once_after_worker_override_and_shares_result(self):
        config = config_for_test()
        args = cli._build_parser().parse_args(["run", "--generator", "all", "--generation-workers", "3"])
        result = measured_result(replace(config, benchmark=replace(config.benchmark, generation_workers=3)))
        with patch("benchmark.cli.load_config", return_value=config), patch("benchmark.cli.resolve_model_meta"), patch(
            "benchmark.cli.load_tasks", return_value=[]
        ), patch("benchmark.cli.validate_tasks", return_value=[]), patch("benchmark.cli._report_quantization_precedence"), patch(
            "benchmark.cli.calibrate", return_value=result
        ) as calibrate, patch("benchmark.cli._execute_benchmark", return_value=score_benchmark([])) as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(cli._run(args), 0)
        calibrate.assert_called_once()
        self.assertEqual(calibrate.call_args.args[0].benchmark.generation_workers, 3)
        self.assertEqual(execute.call_count, 2)
        self.assertTrue(all(call.kwargs["calibration_result"] is result for call in execute.call_args_list))

    def test_execution_saves_before_generation_resumes_without_probes_and_separates_totals(self):
        config = config_for_test()
        config = replace(config, llm=replace(config.llm, temperatures=(0.2,)))
        result = measured_result(config)
        task_score = TaskScore("easy-001", "passed", 7, LlmUsage(10, 20, 30), 10, 10, 1, 9, ("test",), ())
        completed = cli.TemperatureRun(0.2, score_benchmark([task_score]), [task_score])
        args = cli._build_parser().parse_args(["run"])
        with tempfile.TemporaryDirectory() as directory:
            config = replace(config, benchmark=replace(config.benchmark, output_dir=Path(directory)))

            def generate(effective_config, _tasks, **kwargs):
                self.assertTrue((kwargs["run_dir"] / "calibration.json").exists())
                self.assertEqual(effective_config.pi.timeout_seconds, result.timeout_seconds)
                self.assertEqual(effective_config.opencode.timeout_seconds, result.timeout_seconds)
                return [completed]

            with patch("benchmark.cli._run_task_major_temperatures", side_effect=generate), patch(
                "benchmark.cli.calibrate", side_effect=AssertionError("No new probes")
            ), redirect_stdout(io.StringIO()):
                cli._execute_benchmark(config, [], args, calibration_result=result)
                run_dir = next(Path(directory).iterdir())
                summary = json.loads((run_dir / "summary.json").read_text())
                self.assertEqual(summary["calibration"]["tokens_per_second"], result.tokens_per_second)
                self.assertEqual(summary["opencode"]["timeout_seconds"], result.timeout_seconds)
                self.assertEqual(summary["llm_response_time"]["total_seconds"], 7)
                self.assertEqual(summary["llm_token_usage"]["total_tokens"], 30)
                self.assertEqual(summary["score"]["final_score"], 100)
                self.assertIn("Speed calibration", (run_dir / "summary.md").read_text())
                args.resume, args.resume_dir = "easy-001", run_dir
                cli._execute_benchmark(config, [SimpleNamespace(id="easy-001")], args)
                disabled = replace(config, benchmark=replace(config.benchmark, calibration=replace(config.benchmark.calibration, enabled=False)))
                with self.assertRaisesRegex(ValueError, "calibration enabled"):
                    cli._execute_benchmark(disabled, [SimpleNamespace(id="easy-001")], args)

    def test_reports_keep_speed_with_selected_score_and_support_unmeasured_history(self):
        def record(generator, score, speed=None):
            return parse_summary("run", {
                "generator": generator, "model": "model", "score": {"final_score": score},
                "calibration": None if speed is None else {"tokens_per_second": speed, "generation_workers": 2, "timeout_seconds": 2048},
                "llm_token_usage": {"total_tokens": 30}, "llm_response_time": {"total_seconds": 7},
            }, [])

        records = [record("pi", 90), record("pi", 70, 12), record("opencode", 60, 8.25)]
        group = group_results(records)[0]
        self.assertIsNone(group.calibration_pi)
        self.assertEqual(group.calibration_opencode.tokens_per_second, 8.25)
        self.assertEqual(group.avg_score(), 75)
        self.assertEqual(records[2].tokens_per_second, 30 / 7)
        html = render_html([group], Path("results"))
        markdown = render_markdown([group], Path("results"))
        self.assertIn('data-calibration-opencode="8.25"', html)
        self.assertIn('data-key="calibrationOpencode"', html)
        self.assertIn("2 concurrent requests", html)
        self.assertIn("Agent timeout: 2048s", html)
        self.assertIn("| n/a | 8.25 | 90.0 | 60.0 | 75.0 |", markdown)
        self.assertEqual(markdown.splitlines()[6].count("|"), markdown.splitlines()[8].count("|"))


if __name__ == "__main__":
    unittest.main()
