from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from benchmark import cli
from benchmark.aggregate_benchmark_results import group_results, parse_summary, render_html
from benchmark.config import AppConfig, BenchmarkConfig, DockerConfig, OpenCodeConfig, PiConfig, apply_cli_overrides
from benchmark.generation import (GeneratedSolution, OpenCodeGenerator, PiGenerator, OpenCodePreflight, PiPreflight,
                                 PreparedOpenCodeGeneration, PreparedPiGeneration, _agent_prompt)
from benchmark.report import write_summary
from benchmark.runner import CommandResult, DockerRunner, TaskRunResult, write_result_json
from benchmark.scorer import score_task, score_benchmark
from benchmark.solution import ExtractedCode, LlmUsage
from benchmark.tasks import load_tasks, validate_tasks
from benchmark.workspace import capture_project, copy_public_files, restore_project, task_fingerprint


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.task = load_tasks(suite="evolution")[0]
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temporary.cleanup)
        self.config = AppConfig(opencode=OpenCodeConfig(version="test"), pi=PiConfig(version="test"),
                                benchmark=BenchmarkConfig(output_dir=Path(temporary.name)))

    def candidate(self, root, reference=False):
        workspace = root / "candidate"
        workspace.mkdir()
        copy_public_files(self.task, workspace)
        if reference:
            shutil.copytree(self.task.root / "reference", workspace, dirs_exist_ok=True)
        return workspace

    def test_existing_task_loading_and_new_manifest_are_independent(self):
        self.assertEqual(len(load_tasks()), 37)
        self.assertTrue(all(task.suite == "greenfield" for task in load_tasks()))
        self.assertEqual(validate_tasks([self.task]), [])
        updated = apply_cli_overrides(self.config, suite="evolution", generator="all")
        self.assertEqual(updated.benchmark.suite, "evolution")
        self.assertEqual(apply_cli_overrides(self.config, suite="all").benchmark.suite, "all")
        self.assertEqual(len(load_tasks(suite="all")), 43)
        evolution = load_tasks(suite="evolution")
        self.assertEqual(validate_tasks(evolution), [])
        self.assertEqual({difficulty: sum(task.difficulty == difficulty for task in evolution)
                          for difficulty in ("easy", "medium", "hard")}, {"easy": 2, "medium": 2, "hard": 2})
        self.assertEqual(sum(task.score.available_points for task in evolution), 120)
        for task in load_tasks(suite="evolution", role=None):
            for group, weights in (("feature", task.score.tests), ("regression", task.score.regression)):
                source = (task.tests_dir / group / "UnitTests.cs").read_text(encoding="utf-8")
                names = re.findall(r"\[TestMethod\]\s+public\s+(?:async\s+)?(?:Task|void)\s+(\w+)\s*\(", source)
                self.assertEqual(len(names), len(set(names)), (task.id, group))
                self.assertEqual(set(names), set(weights), (task.id, group))
        with self.assertRaises(ValueError):
            apply_cli_overrides(self.config, suite="unknown")

    def test_missing_discovery_is_reported_before_model_requests(self):
        args = cli._build_parser().parse_args(["run", "--suite", "evolution", "--generator", "all"])
        with patch("benchmark.cli.load_config", return_value=self.config), patch(
            "benchmark.cli.resolve_model_meta"
        ) as metadata, patch("benchmark.cli.calibrate") as calibration, patch(
            "benchmark.cli.load_tasks", side_effect=lambda *args, role="scored", **kwargs:
                [] if role == "discovery" else load_tasks(*args, **kwargs)):
            with self.assertRaisesRegex(ValueError, "discovery is incomplete"):
                cli._run(args)
            metadata.assert_not_called()
            calibration.assert_not_called()

    def test_reservation_delivery_keeps_nested_sources_and_hidden_groups_separate(self):
        task = next(task for task in load_tasks(suite="evolution") if task.id == "evolution-medium-001")
        self.assertEqual(validate_tasks([task]), [])
        self.assertEqual(task.score.available_points, 20)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for generator in ("pi", "opencode"):
                task_dir = root / generator
                task_dir.mkdir()
                instance = PiGenerator(self.config) if generator == "pi" else OpenCodeGenerator(self.config)
                prompt = instance._build_user_prompt(task) if generator == "pi" else _agent_prompt(task, self.config.opencode)
                workspace = instance._prepare_workspace(task, task_dir, prompt)
                self.assertFalse((workspace / "tests").exists())
                self.assertFalse((workspace / "reference").exists())
                shutil.copytree(task.root / "reference", workspace, dirs_exist_ok=True)
                snapshot = capture_project(task, workspace, task_dir)
                restored = task_dir / "restored"
                restore_project(task, snapshot, restored)
                self.assertTrue((restored / "src/Controllers/ReservationsController.cs").exists())
                self.assertTrue((restored / "src/Domain/ReservationStore.Rescheduling.cs").exists())
                self.assertEqual((restored / "src/Program.cs").read_bytes(), (task.template_dir / "src/Program.cs").read_bytes())

    def test_every_evolution_reference_roundtrips_through_both_agent_workspaces(self):
        for task in load_tasks(suite="evolution", role=None):
            for generator in ("pi", "opencode"):
                with self.subTest(task=task.id, generator=generator), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    instance = PiGenerator(self.config) if generator == "pi" else OpenCodeGenerator(self.config)
                    prompt = instance._build_user_prompt(task) if generator == "pi" else _agent_prompt(task, self.config.opencode)
                    workspace = instance._prepare_workspace(task, root, prompt)
                    self.assertFalse((workspace / "tests").exists())
                    self.assertFalse((workspace / "reference").exists())
                    shutil.copytree(task.root / "reference", workspace, dirs_exist_ok=True)
                    snapshot = capture_project(task, workspace, root)
                    restored = root / "restored"
                    restore_project(task, snapshot, restored)
                    for file in snapshot.files:
                        self.assertEqual((restored / file.path).read_bytes(), file.content)
                    for name in task.public_files:
                        if not name.startswith("src/"):
                            self.assertEqual((restored / name).read_bytes(), (task.template_dir / name).read_bytes())

    def test_all_suites_run_every_selected_pair_and_share_one_calibration(self):
        config = replace(self.config, llm=replace(self.config.llm, temperatures=(.2,)))
        for generator, expected_generators in (("all", ("opencode", "pi")), ("pi", ("pi",))):
            with self.subTest(generator=generator):
                args = cli._build_parser().parse_args(["run", "--suite", "all", "--generator", generator])
                calibration_result = object()
                with patch("benchmark.cli.load_config", return_value=config), patch(
                    "benchmark.cli.resolve_model_meta"
                ) as metadata, patch("benchmark.cli._report_quantization_precedence"), patch(
                    "benchmark.cli.calibrate", return_value=calibration_result
                ) as calibration, patch(
                    "benchmark.cli._execute_benchmark", return_value=score_benchmark([])
                ) as execute, patch("benchmark.cli.save_calibration"), patch("benchmark.campaign.Campaign.update_pair"), redirect_stdout(io.StringIO()):
                    self.assertEqual(cli._run(args), 0)
                metadata.assert_called_once()
                calibration.assert_called_once()
                self.assertEqual(
                    [(call.args[0].benchmark.suite, call.args[0].benchmark.generator) for call in execute.call_args_list],
                    [(suite, gen) for suite in ("greenfield", "evolution") for gen in expected_generators])
                for call in execute.call_args_list:
                    self.assertTrue(all(task.suite == call.args[0].benchmark.suite for task in call.args[1]))
                    self.assertIs(call.kwargs["calibration_result"], calibration_result)

    def test_all_suites_continue_after_one_failed_pair_and_report_failure(self):
        config = replace(self.config, llm=replace(self.config.llm, temperatures=(.2,)))
        args = cli._build_parser().parse_args(["run", "--suite", "all", "--generator", "all"])
        with patch("benchmark.cli.load_config", return_value=config), patch(
            "benchmark.cli.resolve_model_meta"
        ), patch("benchmark.cli._report_quantization_precedence"), patch("benchmark.cli.calibrate"), patch(
            "benchmark.cli._execute_benchmark", side_effect=[RuntimeError("session failed"),
                score_benchmark([]), score_benchmark([]), score_benchmark([])]
        ) as execute, patch("benchmark.cli.save_calibration"), patch("benchmark.campaign.Campaign.update_pair"), redirect_stdout(io.StringIO()), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(cli._run(args), 1)
            self.assertEqual(execute.call_count, 4)
            self.assertIn("greenfield / opencode", stderr.getvalue())
            self.assertIn("Traceback (most recent call last)", stderr.getvalue())
            self.assertIn("RuntimeError: session failed", stderr.getvalue())

    def test_all_suites_reject_ambiguous_scope_before_model_requests(self):
        for extra_args, message in ((["--task-id", self.task.id], "task_id"),
                                    (["--resume", self.task.id, "--resume-dir", "results/previous"], "Resume"),
                                    (["--resume-campaign", "old", "--resume", self.task.id], "cannot be combined")):
            args = cli._build_parser().parse_args(["run", "--suite", "all", *extra_args])
            with patch("benchmark.cli.load_config", return_value=self.config), patch(
                "benchmark.cli.resolve_model_meta"
            ) as metadata, patch("benchmark.cli.calibrate") as calibration:
                with self.assertRaisesRegex(ValueError, message):
                    cli._run(args)
                metadata.assert_not_called()
                calibration.assert_not_called()

    def test_cli_pipeline_forwards_delivery_for_both_generators(self):
        for generator in ("pi", "opencode"):
            with self.subTest(generator=generator), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                snapshot = capture_project(self.task, self.candidate(root, reference=True))
                result = replace(self.result(tuple(self.task.score.tests), tuple(self.task.score.regression), "passed"),
                                 generator=generator, temperature=.2)
                generated = GeneratedSolution(ExtractedCode(None, ()), 1, LlmUsage(),
                                              generator=generator, project_snapshot=snapshot)

                class Generator:
                    def generate(self, task, artifact_dir):
                        return generated

                config = replace(self.config, llm=replace(self.config.llm, temperatures=(.2,)),
                                 benchmark=BenchmarkConfig(suite="evolution", generator=generator))
                with patch("benchmark.cli.create_solution_generator", return_value=Generator()), patch(
                    "benchmark.cli.DockerRunner.evaluate", return_value=result
                ) as evaluate, redirect_stdout(io.StringIO()):
                    runs = cli._run_task_major_temperatures(config, [self.task], run_dir=root,
                                                            resume_from_index=0, resume_task_id=None)
                self.assertEqual(runs[0].score.final_score, 100)
                self.assertEqual(evaluate.call_args.kwargs["project_snapshot"], snapshot)
                self.assertEqual(evaluate.call_args.kwargs["generator"], generator)
                saved = cli._read_task_result_json(root / "tasks" / self.task.id / "result.json")
                self.assertEqual(saved.generator, generator)
                self.assertEqual(saved.task_fingerprint, snapshot.task_fingerprint)

    def test_delivery_preserves_all_sources_and_records_new_files_and_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.candidate(root, reference=True)
            (workspace / "src/StackStorage.cs").unlink()
            (workspace / "src/RenamedStorage.cs").write_bytes((self.task.template_dir / "src/StackStorage.cs").read_bytes())
            snapshot = capture_project(self.task, workspace, root)
            restored = root / "restored"
            restore_project(self.task, snapshot, restored)
            self.assertFalse((restored / "src/StackStorage.cs").exists())
            self.assertTrue((restored / "src/RenamedStorage.cs").exists())
            self.assertTrue((restored / "src/SimpleStack.TryOperations.cs").exists())
            self.assertIn("SimpleStack.TryOperations.cs", (root / "changes.diff").read_text())
            self.assertEqual(json.loads((root / "delivery.json").read_text())["deleted_files"], ["src/StackStorage.cs"])
            self.assertFalse((restored / "tests").exists())

    def test_immutable_project_files_and_unexpected_sources_cannot_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self.candidate(root)
            project = workspace / self.task.build_project
            original = project.read_bytes()
            project.write_bytes(original + b"<!-- changed -->")
            with self.assertRaisesRegex(ValueError, "Immutable"):
                capture_project(self.task, workspace)
            project.write_bytes(original)
            (workspace / "src/Directory.Build.targets").write_text("<Project />")
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                capture_project(self.task, workspace)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                restore_project(self.task, replace(capture_project(self.task, self.task.template_dir),
                                                  deleted_files=("../outside.cs",)), root / "restored")

    def test_both_generators_receive_working_project_and_return_complete_delivery(self):
        for generator in ("pi", "opencode"):
            for precreated in (False, True):
                with self.subTest(generator=generator, precreated=precreated), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    instance = PiGenerator(self.config) if generator == "pi" else OpenCodeGenerator(self.config)
                    prompt = instance._build_user_prompt(self.task) if generator == "pi" else _agent_prompt(self.task, self.config.opencode)
                    self.assertNotIn("Do not declare a C# namespace", prompt)
                    self.assertNotIn("exactly the required generated file", prompt)
                    workspace = instance._prepare_workspace(self.task, root, prompt)
                    self.assertEqual((workspace / "src/SimpleStack.cs").read_bytes(), (self.task.template_dir / "src/SimpleStack.cs").read_bytes())
                    self.assertFalse((workspace / "tests").exists())
                    self.assertFalse((workspace / "reference").exists())
                    shutil.copytree(self.task.root / "reference", workspace, dirs_exist_ok=True)
                    if generator == "pi":
                        prepared = PreparedPiGeneration(self.task, root, workspace, root / "pi-home",
                                                        PiPreflight("pi", 0, ""), "session", [], precreated)
                    else:
                        prepared = PreparedOpenCodeGeneration(self.task, root, workspace,
                                                              OpenCodePreflight("test", "test", "opencode", 0, ""),
                                                              "session", [], precreated)
                    with patch("benchmark.generation._run_docker_command", return_value=CommandResult(0, "", "")), patch("benchmark.generation._remove_container"):
                        generated = instance.run_prepared(prepared)
                    self.assertIsNone(generated.extracted.error)
                    self.assertIsNotNone(generated.project_snapshot)
                    self.assertIn("src/SimpleStack.TryOperations.cs", [file.path for file in generated.project_snapshot.files])

    def result(self, feature=(), regression=(), status="tests_failed"):
        return TaskRunResult(self.task.id, status, 1, LlmUsage(), None, None, None,
                             tuple(feature) + tuple(regression), (), (), suite="evolution",
                             task_fingerprint=task_fingerprint(self.task), test_group_results={
                                 "feature": {"passed_tests": list(feature)},
                                 "regression": {"passed_tests": list(regression)},
                             })

    def test_noop_feature_regression_and_terminal_failures_have_fixed_denominator(self):
        features = tuple(self.task.score.tests)
        regressions = tuple(self.task.score.regression)
        cases = (((), regressions, "tests_failed", 0, 0, 1),
                 (features, regressions, "passed", 10, 1, 1),
                 (features, regressions[:-1], "tests_failed", 8, 1, .8),
                 (features[:-1], regressions[:-1], "tests_failed", 6.4, .8, .8),
                 (features, regressions, "build_failed", 0, 0, 0),
                 (features, regressions, "infrastructure_error", 0, 0, 0))
        for feature, regression, status, earned, f, r in cases:
            score = score_task(self.task, self.result(feature, regression, status))
            self.assertAlmostEqual(score.earned_points, earned)
            self.assertEqual(score.available_points, 10)
            self.assertEqual(score.feature_ratio, f)
            self.assertEqual(score.regression_ratio, r)

    def test_runner_compiles_groups_independently_and_missing_results_do_not_pass(self):
        for missing_results in (False, True):
            with self.subTest(missing_results=missing_results), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                snapshot = capture_project(self.task, self.candidate(root))
                runner = DockerRunner(DockerConfig())
                commands = []

                def execute(container, workdir, command):
                    commands.append(command)
                    return CommandResult(1 if "build tests/feature/" in command else 0, "", "")

                def copy_results(container, workdir, destination):
                    if not missing_results:
                        results = destination / "TestResults/regression"
                        results.mkdir(parents=True)
                        results.joinpath("result.trx").write_text("<TestRun>" + "".join(
                            f'<UnitTestResult testName="{name}" outcome="Passed" />'
                            for name in self.task.score.regression) + "</TestRun>")
                    return CommandResult(0, "", "")

                with patch.object(runner, "_create_container", return_value=CommandResult(0, "", "")), patch.object(
                    runner, "_copy_workspace_to_container", return_value=CommandResult(0, "", "")
                ), patch.object(runner, "_exec_in_container", side_effect=execute), patch.object(
                    runner, "_copy_results_from_container", side_effect=copy_results
                ), patch.object(runner, "_remove_container"):
                    result = runner.evaluate(self.task, ExtractedCode(None, ()), artifact_dir=root,
                                             llm_response_time_seconds=0, llm_usage=LlmUsage(), project_snapshot=snapshot)
                score = score_task(self.task, result)
                self.assertEqual(score.feature_ratio, 0)
                self.assertEqual(score.regression_ratio, 0 if missing_results else 1)
                self.assertEqual(result.status, "tests_failed")
                self.assertTrue(any("test tests/regression/" in command for command in commands))
                self.assertFalse(any("test tests/feature/" in command for command in commands))

    def test_result_resume_and_summary_keep_group_diagnostics_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.result(tuple(self.task.score.tests), tuple(self.task.score.regression), "passed")
            write_result_json(root / "result.json", result)
            loaded = cli._read_task_result_json(root / "result.json")
            self.assertEqual(score_task(self.task, loaded).earned_points, 10)
            changed = replace(self.task, version="2")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                cli._load_existing_task_score(changed, root / "result.json", [None], [],
                                              task_index=0, row_index=0, expected_temperature=.2, prefix="")
            config = replace(self.config, benchmark=BenchmarkConfig(suite="evolution"))
            score = score_task(self.task, loaded)
            write_summary(root, config=config, score=score_benchmark([score]), task_scores=[score])
            summary = json.loads((root / "summary.json").read_text())
            self.assertEqual(summary["suite"], "evolution")
            self.assertEqual(summary["tasks"][0]["regression_ratio"], 1)
            self.assertIn("Existing behavior preserved", (root / "summary.md").read_text())

    def test_aggregate_never_merges_evolution_with_greenfield(self):
        results = [parse_summary("greenfield", {"generator": "pi", "model": "model", "score": {"final_score": 80}}, []),
                   parse_summary("evolution", {"suite": "evolution", "generator": "pi", "model": "model", "score": {"final_score": 40}}, [])]
        groups = group_results(results)
        self.assertEqual(len(groups), 2)
        self.assertEqual({group.suite: group.score_pi for group in groups}, {"greenfield": 80, "evolution": 40})
        self.assertIn('data-suite="evolution"', render_html(groups, Path("results")))


if __name__ == "__main__":
    unittest.main()
