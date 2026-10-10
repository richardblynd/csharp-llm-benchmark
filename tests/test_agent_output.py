from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from benchmark.config import AppConfig, OpenCodeConfig, PiConfig, apply_cli_overrides, load_config
from benchmark.agent_events import copy_compact_events, run_with_compact_events
from benchmark.generation import (
    OpenCodeGenerator,
    OpenCodePreflight,
    PiGenerator,
    PiPreflight,
    PreparedOpenCodeGeneration,
    PreparedPiGeneration,
    _opencode_session_missing_model_result,
    _parse_agentic_usage,
    _parse_opencode_error,
    _run_docker_command,
)
from benchmark.runner import CommandResult
from benchmark.tasks import load_tasks


class AgentOutputTests(unittest.TestCase):
    def test_compact_capture_discards_enormous_updates_with_bounded_memory(self):
        script = (
            "import sys; out=sys.stdout.buffer; "
            "out.write(b'{\"type\":\"message_update\",\"text\":\"'); "
            "[out.write(b'x'*65536) for _ in range(512)]; "
            "out.write(b'\"}\\n{\"type\":\"message_end\",\"message\":{\"usage\":{\"output\":3}}}\\n'); "
            "sys.stderr.write('diagnostic'); sys.exit(7)"
        )
        with tempfile.TemporaryDirectory() as directory:
            tracemalloc.start()
            try:
                result = _run_docker_command(
                    [sys.executable, "-c", script], output_dir=Path(directory),
                    output_prefix="pi", compact_events=True, timeout=20,
                )
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertLess(peak, 2 * 1024**2)
            self.assertEqual(result.exit_code, 7)
            self.assertLess(result.stdout_path.stat().st_size, 100)
            self.assertEqual(_parse_agentic_usage(result.stdout_path, generator="pi").completion_tokens, 3)
            self.assertEqual(result.stderr_path.read_text(), "diagnostic")

    def test_compaction_keeps_unknown_errors_tools_and_incomplete_final_events(self):
        records = [
            b'{"type":"message_update","text":"partial"}\n',
            b'{"type":"tool_execution_update","text":"partial"}\n',
            b'{"type":"message_end","message":{"text":"final"}}\n',
            b'{"type":"tool_execution_end","result":{"isError":true}}\n',
            b'{"type":"compaction_end","aborted":false}\n',
            b'{"type":"error","error":"failed"}\n',
            b'{"type":"future_event"}\n',
            b'non-json diagnostic\n',
            b'{"type":"message_end","unfinished":"',
        ]
        output = io.BytesIO()
        copy_compact_events(io.BytesIO(b"".join(records)), output)
        self.assertEqual(output.getvalue(), b"".join(records[2:]))

    def test_final_pi_usage_is_identical_for_compact_and_full_logs(self):
        message = {"role": "assistant", "usage": {
            "input": 10, "output": 5, "totalTokens": 15, "reasoning": 2,
        }}
        events = [
            {"type": "message_update", "message": message},
            {"type": "message_end", "message": message},
            {"type": "turn_end", "message": message},
            {"type": "agent_end", "messages": [message]},
            {"type": "compaction_end", "result": {"usage": {
                "input": 3, "output": 1, "totalTokens": 4, "reasoning": 1,
            }}},
        ]
        raw = b"".join(json.dumps(event).encode() + b"\n" for event in events)
        compact = io.BytesIO()
        copy_compact_events(io.BytesIO(raw), compact)
        full_usage = _parse_agentic_usage(raw.decode(), generator="pi")
        compact_usage = _parse_agentic_usage(compact.getvalue().decode(), generator="pi")
        self.assertEqual(full_usage, compact_usage)
        self.assertEqual(full_usage.prompt_tokens, 13)
        self.assertEqual(full_usage.completion_tokens, 6)
        self.assertEqual(full_usage.total_tokens, 19)
        self.assertEqual(full_usage.reasoning_tokens, 3)

    def test_capture_failure_stops_agent_instead_of_waiting_for_deadline(self):
        class FailingDestination(io.BytesIO):
            def write(self, data):
                raise OSError("disk full")

        with tempfile.TemporaryFile() as stderr:
            with self.assertRaisesRegex(RuntimeError, "disk full"):
                run_with_compact_events(
                    [sys.executable, "-c", "import time; print('event',flush=True); time.sleep(20)"],
                    stdout=FailingDestination(), stderr=stderr, timeout=10, env={},
                )

    def test_parallel_large_output_does_not_accumulate_in_python_memory(self):
        # Exercise the actual subprocess path at the user's concurrency, without
        # Docker or inference. The former capture accumulated 64 MiB here.
        script = (
            "import sys; chunk=b'x'*65536; "
            "[(sys.stdout.buffer.write(chunk), sys.stderr.buffer.write(chunk)) "
            "for _ in range(64)]"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(8):
                (root / str(index)).mkdir()
            tracemalloc.start()
            try:
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(
                        _run_docker_command, [sys.executable, "-c", script],
                        output_dir=root / str(index), output_prefix="pi", timeout=20,
                    ) for index in range(8)]
                    results = [future.result() for future in futures]
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertLess(peak, 8 * 1024**2)
            for result in results:
                self.assertEqual(result.exit_code, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout_path.stat().st_size, 4 * 1024**2)
                self.assertEqual(result.stderr_path.stat().st_size, 4 * 1024**2)

    def test_logs_are_visible_before_the_session_finishes(self):
        script = (
            "import pathlib,sys,time; "
            "sys.stdout.write('event\\n'); sys.stdout.flush(); "
            "sys.stderr.write('diagnostic\\n'); sys.stderr.flush(); "
            "release=pathlib.Path(sys.argv[1]); "
            "exec('while not release.exists(): time.sleep(0.02)')"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "release"
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _run_docker_command, [sys.executable, "-c", script, str(release)],
                    output_dir=root, output_prefix="pi", timeout=10,
                )
                try:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        log = root / "pi-stderr.log"
                        if log.exists() and log.stat().st_size:
                            break
                        if future.done():
                            self.fail(f"Session exited early: {future.result()}")
                        time.sleep(0.02)
                    self.assertFalse(future.done())
                    self.assertEqual((root / "pi-events.jsonl").read_text(), "event\n")
                    self.assertEqual(log.read_text(), "diagnostic\n")
                finally:
                    release.touch()
                self.assertEqual(future.result().exit_code, 0)

    def test_timeout_preserves_partial_output_and_container_policy(self):
        script = "import sys,time; print('partial',flush=True); time.sleep(10)"
        for keep, compact in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(keep=keep, compact=compact), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                real_run = subprocess.run

                def run(command, **kwargs):
                    if command[:3] == ["docker", "rm", "-f"]:
                        return subprocess.CompletedProcess(command, 0, "", "")
                    return real_run(command, **kwargs)

                with patch("benchmark.generation.subprocess.run", side_effect=run) as subprocess_run:
                    result = _run_docker_command(
                        [sys.executable, "-c", script, "--name", "test-session"],
                        timeout=0.5, keep_on_timeout=keep, output_dir=root,
                        output_prefix="pi",
                        compact_events=compact,
                    )
                self.assertEqual(result.exit_code, 124)
                self.assertTrue(result.timed_out)
                self.assertEqual(result.stdout_path.read_text(), "partial\n")
                self.assertEqual(result.container_name, "test-session" if keep else None)
                removals = [call for call in subprocess_run.call_args_list
                            if call.args[0][:3] == ["docker", "rm", "-f"]]
                self.assertEqual(len(removals), 0 if keep else 1)

    def test_short_install_commands_still_return_text(self):
        result = _run_docker_command([
            sys.executable, "-c", "import sys; print('version'); print('note',file=sys.stderr)",
        ])
        self.assertEqual(result.stdout.strip(), "version")
        self.assertEqual(result.stderr.strip(), "note")
        self.assertIsNone(result.stdout_path)

    def test_large_log_parsing_is_incremental_and_tolerates_partial_tail(self):
        event = json.dumps({
            "type": "step_finish",
            "part": {"type": "step-finish", "tokens": {"input": 7, "output": 3, "total": 10}},
            "text": "x" * 4096,
        }).encode() + b"\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            with path.open("wb") as stream:
                for _ in range(8192):
                    stream.write(event)
                stream.write(b'not-json\n[]\n{"type":"error","error":{"data":{"message":"failed"}}}\n')
                stream.write(b'{"unfinished":"\xe2\x82')
            tracemalloc.start()
            try:
                with patch.object(Path, "read_text", side_effect=AssertionError("Whole-file read")):
                    usage = _parse_agentic_usage(path)
                    error = _parse_opencode_error(path)
                    missing = _opencode_session_missing_model_result(path)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertLess(peak, 2 * 1024**2)
            self.assertEqual(usage.prompt_tokens, 7 * 8192)
            self.assertEqual(usage.completion_tokens, 3 * 8192)
            self.assertEqual(usage.total_tokens, 10 * 8192)
            self.assertEqual(error, "failed")
            self.assertFalse(missing)


class GeneratorFileOutputTests(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig(
            opencode=OpenCodeConfig(version="test-opencode"),
            pi=PiConfig(version="test-pi"),
        )
        self.task = load_tasks("easy")[0]

    def prepared(self, root, generator, precreated):
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / self.task.generated_file).write_text("public class Solution {}", encoding="utf-8")
        if generator == "pi":
            return PreparedPiGeneration(
                self.task, root, workspace, root / "pi-home", PiPreflight("pi", 0, ""),
                "test-session", ["docker", "create"], precreated,
            )
        return PreparedOpenCodeGeneration(
            self.task, root, workspace, OpenCodePreflight("test", "test", "opencode", 0, ""),
            "test-session", ["docker", "create"], precreated,
        )

    def test_both_generators_use_file_output_for_normal_and_precreated_sessions(self):
        event = {"type": "message_end", "message": {"usage": {"input": 7, "output": 3, "totalTokens": 10}}}
        for generator in ("pi", "opencode"):
            for precreated in (False, True):
                with self.subTest(generator=generator, precreated=precreated), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    prepared = self.prepared(root, generator, precreated)
                    instance = PiGenerator(self.config) if generator == "pi" else OpenCodeGenerator(self.config)

                    def execute(command, **kwargs):
                        self.assertEqual(kwargs["output_dir"], root)
                        self.assertEqual(kwargs["output_prefix"], generator)
                        if generator == "pi":
                            self.assertTrue(kwargs["compact_events"])
                        return _run_docker_command(
                            [sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", json.dumps(event) + "\n"],
                            **kwargs,
                        )

                    with patch("benchmark.generation._run_docker_command", side_effect=execute), patch(
                        "benchmark.generation._remove_container"
                    ):
                        result = instance.run_prepared(prepared)
                    self.assertEqual(result.llm_usage.completion_tokens, 3)
                    self.assertIsNotNone(result.extracted.code)
                    self.assertTrue((root / f"{generator}-events.jsonl").exists())
                    self.assertTrue((root / f"{generator}-stderr.log").exists())
                    if generator == "opencode":
                        self.assertEqual((root / "response.md").read_bytes(), (root / "opencode-events.jsonl").read_bytes())

    def test_pi_full_log_setting_loads_and_survives_cli_overrides(self):
        self.assertFalse(self.config.pi.full_event_log)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text('benchmark:\n  generator: pi\npi:\n  version: "test"\n  full_event_log: true\n')
            config = load_config(path)
            self.assertTrue(apply_cli_overrides(config, generator="pi").pi.full_event_log)
            path.write_text('pi:\n  full_event_log: invalid\n')
            with self.assertRaisesRegex(ValueError, "pi.full_event_log"):
                load_config(path)

    def test_pi_full_log_bypasses_filter_for_both_session_paths(self):
        config = replace(self.config, pi=replace(self.config.pi, full_event_log=True))
        for precreated in (False, True):
            with self.subTest(precreated=precreated), tempfile.TemporaryDirectory() as directory:
                prepared = self.prepared(Path(directory), "pi", precreated)
                instance = PiGenerator(config)
                with patch("benchmark.generation._run_docker_command", return_value=CommandResult(0, "", "")) as run, patch(
                    "benchmark.generation._remove_container"
                ):
                    instance._execute_session(prepared)
                self.assertFalse(run.call_args.kwargs["compact_events"])

    def test_precreated_timeout_keeps_file_metadata_and_expected_container_cleanup(self):
        for generator in ("pi", "opencode"):
            for keep in (False, True):
                with self.subTest(generator=generator, keep=keep), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    prepared = self.prepared(root, generator, True)
                    agent_config = replace(getattr(self.config, generator), keep_timed_out_containers=keep)
                    config = replace(self.config, **{generator: agent_config})
                    instance = PiGenerator(config) if generator == "pi" else OpenCodeGenerator(config)
                    output = root / f"{generator}-events.jsonl"
                    output.write_text('{"usage":{"output":3}}\n')
                    result = CommandResult(124, "", "", timed_out=True, stdout_path=output)
                    with patch("benchmark.generation._run_docker_command", return_value=result), patch(
                        "benchmark.generation._remove_container"
                    ) as remove:
                        method = instance._start_precreated_pi if generator == "pi" else instance._start_precreated_opencode
                        completed = method(prepared)
                    self.assertEqual(completed.stdout_path, output)
                    self.assertTrue(completed.timed_out)
                    self.assertEqual(remove.call_count, 0 if keep else 1)

    def test_opencode_retry_reads_fresh_session_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = self.prepared(root, "opencode", True)
            (prepared.workspace / self.task.generated_file).unlink()
            instance = OpenCodeGenerator(self.config)
            attempts = []

            def execute(command, **kwargs):
                attempts.append(command)
                prefix = kwargs["output_prefix"]
                output = root / f"{prefix}-events.jsonl"
                stderr = root / f"{prefix}-stderr.log"
                output.write_text("" if len(attempts) == 1 else '{"usage":{"output":5}}\n')
                stderr.write_text("")
                if len(attempts) > 1:
                    (prepared.workspace / self.task.generated_file).write_text("public class Solution {}")
                return CommandResult(0, "", "", stdout_path=output, stderr_path=stderr)

            with patch("benchmark.generation._run_docker_command", side_effect=execute), patch(
                "benchmark.generation._remove_container"
            ), patch.object(instance, "_opencode_docker_command", return_value=["docker", "run"]):
                result = instance.run_prepared(prepared)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(result.opencode_metadata.attempts, 2)
            self.assertEqual(result.llm_usage.completion_tokens, 5)
            self.assertIn("events_bytes=0", (root / "opencode-retries.log").read_text())


if __name__ == "__main__":
    unittest.main()
