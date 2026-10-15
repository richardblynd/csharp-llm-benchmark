from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark import cli
from benchmark.config import AppConfig, BenchmarkConfig, CalibrationConfig, DiscoveryConfig, OpenCodeConfig, PiConfig
from benchmark.generation import GeneratedSolution, OpenCodeGenerator, PiGenerator
from benchmark.runner import CommandResult
from benchmark.solution import ExtractedCode, LlmUsage
from benchmark.tasks import load_tasks


class PreparationFailureTests(unittest.TestCase):
    def test_matrix_survives_unavailable_cwd_between_runs(self):
        cwd = Path.cwd()
        tasks_by_suite = {suite: load_tasks(suite=suite)[:1]
                          for suite in ("greenfield", "evolution")}
        with tempfile.TemporaryDirectory(dir=cwd / ".cache/test-temp") as directory:
            root = Path(directory)
            config = AppConfig(
                benchmark=BenchmarkConfig(suite="all", generator="all",
                                          output_dir=root.relative_to(cwd) / "results",
                                          calibration=CalibrationConfig(enabled=False)),
                pi=PiConfig(version="matrix-test", cache_dir=root.relative_to(cwd) / "pi-cache"),
                opencode=OpenCodeConfig(version="matrix-test", cache_dir=root.relative_to(cwd) / "opencode-cache"),
            )
            config = replace(config, llm=replace(config.llm, temperatures=(.2,),
                                                 discovery=DiscoveryConfig(enabled=False)))
            for generator_type in (PiGenerator, OpenCodeGenerator):
                instance = generator_type(config)
                install = instance._pi_install_dir() if generator_type is PiGenerator else instance._opencode_install_dir()
                binary = install / "node_modules/.bin/pi"
                binary.parent.mkdir(parents=True)
                binary.touch()
            args = cli._build_parser().parse_args(["run"])
            cwd_unavailable = False
            completed = []
            execute = cli._execute_benchmark
            original_resolve = Path.resolve

            def resolve(path, *args, **kwargs):
                if cwd_unavailable and not path.is_absolute():
                    raise FileNotFoundError(2, "No such file or directory")
                return original_resolve(path, *args, **kwargs)

            def finish_run(*args, **kwargs):
                nonlocal cwd_unavailable
                score = execute(*args, **kwargs)
                completed.append((args[0].benchmark.suite, args[0].benchmark.generator))
                cwd_unavailable = True
                return score

            skipped = lambda generator: GeneratedSolution(
                ExtractedCode(None, (), "model deliberately skipped"), 0, LlmUsage(), generator=generator)
            with patch.object(Path, "resolve", resolve), patch("benchmark.cli.load_config", return_value=config), patch(
                "benchmark.cli.load_tasks", side_effect=lambda *args, suite, **kwargs: tasks_by_suite[suite]
            ), patch("benchmark.cli.resolve_model_meta", return_value=None), patch("benchmark.cli._report_quantization_precedence"), patch(
                "benchmark.cli.is_local_server", return_value=False
            ), patch("benchmark.cli._execute_benchmark", side_effect=finish_run), patch.object(
                PiGenerator, "_ensure_pi_installed", return_value=(0, "cached pi verified")
            ), patch.object(OpenCodeGenerator, "_ensure_opencode_installed", return_value=CommandResult(0, "cached opencode verified", "")), patch.object(
                PiGenerator, "run_prepared", return_value=skipped("pi")
            ), patch.object(OpenCodeGenerator, "run_prepared", return_value=skipped("opencode")), patch(
                "benchmark.cli.DashboardRenderer.render"
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                exit_code = cli._run(args)
            self.assertEqual(exit_code, 0, stderr.getvalue())
            self.assertEqual(completed, [(suite, generator) for suite in ("greenfield", "evolution")
                                         for generator in ("opencode", "pi")])
            self.assertEqual(len(list((root / "results").glob("*/*/*/summary.json"))), 4)

    def test_queue_keeps_running_when_cwd_becomes_unavailable_after_preflight(self):
        cwd = Path.cwd()
        tasks = load_tasks(suite="evolution")
        for generator in ("pi", "opencode"):
            self._check_unavailable_cwd(cwd, tasks, generator)

    def _check_unavailable_cwd(self, cwd, tasks, generator):
        with self.subTest(generator=generator), tempfile.TemporaryDirectory(dir=cwd / ".cache/test-temp") as directory:
            root = Path(directory)
            config = AppConfig(
                benchmark=BenchmarkConfig(suite="evolution", generator=generator, generation_workers=2,
                                          output_dir=root.relative_to(cwd) / "results",
                                          calibration=CalibrationConfig(enabled=False)),
                pi=PiConfig(version="cwd-test", cache_dir=root.relative_to(cwd) / "pi-cache"),
                opencode=OpenCodeConfig(version="cwd-test", cache_dir=root.relative_to(cwd) / "opencode-cache"),
            )
            config = replace(config, llm=replace(config.llm, temperatures=(.2,)))
            generator_type = PiGenerator if generator == "pi" else OpenCodeGenerator
            instance = generator_type(config)
            install = instance._pi_install_dir() if generator == "pi" else instance._opencode_install_dir()
            binary = install / f"node_modules/.bin/{generator}"
            binary.parent.mkdir(parents=True)
            binary.touch()
            args = cli._build_parser().parse_args(["run", "--suite", "evolution"])
            skipped = GeneratedSolution(ExtractedCode(None, (), "model deliberately skipped"), 0,
                                        LlmUsage(), generator=generator)
            original_resolve = Path.resolve
            cwd_unavailable = False

            def resolve(path, *args, **kwargs):
                # POSIX needs getcwd to resolve relative paths; Windows realpath
                # also calls it for absolute paths, so model the WSL failure here.
                if cwd_unavailable and not path.is_absolute():
                    raise FileNotFoundError(2, "No such file or directory")
                return original_resolve(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolve):
                def preflight_finished():
                    nonlocal cwd_unavailable
                    cwd_unavailable = True
                    return (0, "cached pi install verified") if generator == "pi" else CommandResult(0, "cached opencode verified", "")

                method = "_ensure_pi_installed" if generator == "pi" else "_ensure_opencode_installed"
                with patch.object(generator_type, method, side_effect=preflight_finished), patch.object(
                    generator_type, "run_prepared", return_value=skipped
                ), patch("benchmark.cli.DashboardRenderer.render"), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    score = cli._execute_benchmark(config, tasks, args)
            self.assertEqual(len(score.task_scores), len(tasks))
            self.assertTrue(all(task.status == "extraction_error" for task in score.task_scores))

    def test_preparation_error_is_saved_and_printed_after_last_dashboard_draw(self):
        task = load_tasks(suite="evolution")[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig(benchmark=BenchmarkConfig(suite="evolution", generator="pi"),
                               pi=PiConfig(version="test"), opencode=OpenCodeConfig(version="test"))
            config = replace(config, llm=replace(config.llm, temperatures=(.2,)))
            events = []
            original_print = cli.traceback.print_exception

            def record_exception(exc):
                events.append("exception")
                original_print(exc)

            with patch.object(PiGenerator, "preflight"), patch.object(
                PiGenerator, "prepare", side_effect=FileNotFoundError(2, "No such file or directory")
            ), patch("benchmark.cli.DashboardRenderer.render", side_effect=lambda: events.append("dashboard")), patch(
                "benchmark.cli.traceback.print_exception", side_effect=record_exception
            ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaisesRegex(RuntimeError, "Preparation failed"):
                    cli._run_task_major_temperatures(config, [task], run_dir=root,
                                                    resume_from_index=0, resume_task_id=None)
            self.assertEqual(events[-1], "exception", "Dashboard redraw must not overwrite the exception")
            log = root / "tasks" / task.id / "error.log"
            self.assertTrue(log.is_file())
            self.assertIn("FileNotFoundError", log.read_text(encoding="utf-8"))
            self.assertIn("FileNotFoundError", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
