"""Opt-in evaluation against the real, prebuilt Docker image."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from benchmark.config import DockerConfig
from benchmark.runner import DockerRunner
from benchmark.scorer import score_task, score_benchmark
from benchmark.solution import ExtractedCode, LlmUsage
from benchmark.tasks import load_tasks
from benchmark.workspace import capture_project, copy_public_files


@unittest.skipUnless(os.environ.get("BENCHMARK_DOCKER_TESTS") == "1",
                     "Set BENCHMARK_DOCKER_TESTS=1 to run real Docker evaluations")
class EvolutionDockerTests(unittest.TestCase):
    def test_existing_greenfield_sqlite_reference_loads_native_dependency(self):
        task = next(task for task in load_tasks("hard", tasks_root=Path(__file__).resolve().parents[1] / "tasks")
                    if task.id == "hard-012")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = DockerRunner(DockerConfig()).evaluate(task,
                ExtractedCode((task.root / "reference/Solution.cs").read_text(encoding="utf-8"), ()),
                artifact_dir=root, llm_response_time_seconds=0, llm_usage=LlmUsage())
            diagnostic = "\n".join(path.read_text(encoding="utf-8")[-3000:] for path in root.glob("*.log"))
            self.assertEqual(score_benchmark([score_task(task, result)]).final_score, 100, diagnostic)

    def test_catalog_search_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-easy-002", "src/Controllers/ProductsController.cs",
                                  "StringComparison.OrdinalIgnoreCase", "StringComparison.Ordinal",
                                  "src/Controllers/ProductsController.cs",
                                  'CreatedAtAction(nameof(Get), new { id = request!.Id }, request)', 'Ok(request)')

    def test_notification_fallback_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-medium-002", "src/NotificationRouter.Fallback.cs",
                                  "if (attempt.Succeeded)", "if (true)",
                                  "src/Channels.cs", 'NotificationChannel("sms",', 'NotificationChannel("text",')

    def test_inventory_reservations_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-hard-001", "src/InventoryService.Rules.cs",
                                  "quantity < ReservedQuantity(productId, transaction)", "quantity < 0",
                                  "src/InventoryService.cs", "clock.GetUtcNow().ToString", "DateTimeOffset.UnixEpoch.ToString")

    def test_outbox_retry_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-hard-002", "src/OutboxWorker.cs",
                                  "delayTicks = delayTicks > capTicks / 2 ? capTicks : delayTicks * 2;",
                                  "delayTicks = policy.InitialDelay.Ticks;",
                                  "src/OutboxStore.cs", "return value.Trim();", "return value;")

    def _check_expanded_task(self, task_id, feature_path, feature_before, feature_after,
                             regression_path, regression_before, regression_after):
        task = next(task for task in load_tasks(
                    tasks_root=Path(__file__).resolve().parents[1] / "tasks", suite="evolution", role=None) if task.id == task_id)
        runner = DockerRunner(DockerConfig())
        for label in ("starter", "reference", "broken-feature", "broken-regression"):
            with self.subTest(task=task_id, label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                candidate = root / "candidate"
                copy_public_files(task, candidate)
                if label != "starter":
                    shutil.copytree(task.root / "reference", candidate, dirs_exist_ok=True)
                if label in {"broken-feature", "broken-regression"}:
                    name, before, after = ((feature_path, feature_before, feature_after) if label == "broken-feature"
                                           else (regression_path, regression_before, regression_after))
                    source = candidate / name
                    text = source.read_text(encoding="utf-8")
                    self.assertIn(before, text, "Mutation must exercise the intended source")
                    source.write_text(text.replace(before, after), encoding="utf-8")
                result = runner.evaluate(task, ExtractedCode(None, ()), artifact_dir=root,
                                         llm_response_time_seconds=0, llm_usage=LlmUsage(),
                                         project_snapshot=capture_project(task, candidate, root))
                score = score_task(task, result)
                diagnostic = str(result.test_group_results) + "\n" + "\n".join(
                    path.name + "\n" + path.read_text(encoding="utf-8")[-3000:] for path in root.glob("*.log"))
                self.assertIsNone(result.infrastructure_error, diagnostic)
                self.assertEqual(result.build.exit_code, 0, diagnostic)
                if label == "starter":
                    self.assertEqual(score.feature_ratio, 0, diagnostic)
                    self.assertEqual(score.regression_ratio, 1, diagnostic)
                elif label == "reference":
                    self.assertEqual(score.feature_ratio, 1, diagnostic)
                    self.assertEqual(score.regression_ratio, 1, diagnostic)
                elif label == "broken-feature":
                    self.assertLess(score.feature_ratio, 1, diagnostic)
                    self.assertEqual(score.regression_ratio, 1, diagnostic)
                else:
                    self.assertEqual(score.feature_ratio, 1, diagnostic)
                    self.assertLess(score.regression_ratio, 1, diagnostic)
                print(f"{task_id} {label}: feature={score.feature_ratio:.0%}, "
                      f"regression={score.regression_ratio:.0%}, score={score_benchmark([score]).final_score}", flush=True)

    def test_discovery_collections_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-discovery-easy-001", "src/OrderedSet.Movement.cs",
            "items.Insert(target + (after ? 1 : 0), stored);", "items.Insert(0, stored);",
            "src/OrderedSet.cs", "if (Contains(item)) return false;", "if (Contains(item)) return true;")

    def test_discovery_composition_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-discovery-medium-001", "src/JsonFormatter.cs",
            "name=r.Name", "title=r.Name", "src/Reports.cs", '"name,value\\n"', '"label,value\\n"')

    def test_discovery_http_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-discovery-medium-002", "src/TodoStore.Completion.cs",
            "return ids.Select", "return ids.Reverse().Select", "src/Program.cs",
            '$"/todos/{todo.Id}"', '$"/tasks/{todo.Id}"')

    def test_discovery_persistence_starter_reference_and_mutants(self):
        self._check_expanded_task("evolution-discovery-hard-001", "src/CounterStore.CompareExchange.cs",
            "if(current!=expected)", "if(false)", "src/CounterStore.cs",
            "checked(Read(name,tx)+delta)", "unchecked(Read(name,tx)+delta)")

    def test_starter_reference_and_deliberate_regression(self):
        task = load_tasks(suite="evolution")[0]
        runner = DockerRunner(DockerConfig())
        cases = (("starter", False, False, 0, 0, 1),
                 ("reference", True, False, 100, 1, 1),
                 ("regression", True, True, 80, 1, .8))
        for label, reference, break_old_behavior, expected, feature, regression in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                candidate = root / "candidate"
                copy_public_files(task, candidate)
                if reference:
                    shutil.copytree(task.root / "reference", candidate, dirs_exist_ok=True)
                if break_old_behavior:
                    source = candidate / "src/StackStorage.cs"
                    source.write_text(source.read_text().replace(
                        'throw new InvalidOperationException("The stack is empty.");',
                        "return default!;"), encoding="utf-8")
                snapshot = capture_project(task, candidate, root)
                result = runner.evaluate(task, ExtractedCode(None, ()), artifact_dir=root,
                                         llm_response_time_seconds=0, llm_usage=LlmUsage(),
                                         project_snapshot=snapshot)
                score = score_task(task, result)
                diagnostic = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.log"))
                self.assertEqual(score.feature_ratio, feature, diagnostic)
                self.assertEqual(score.regression_ratio, regression, diagnostic)
                self.assertEqual(score_benchmark([score]).final_score, expected, diagnostic)
                print(f"{label}: feature={feature:.0%}, regression={regression:.0%}, score={expected}", flush=True)

    def test_reservation_feature_detects_nonatomic_changes_and_old_contract_regressions(self):
        task = next(task for task in load_tasks(suite="evolution") if task.id == "evolution-medium-001")
        runner = DockerRunner(DockerConfig())
        for label in ("starter", "reference", "broken-atomicity", "broken-old-contract"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                candidate = root / "candidate"
                copy_public_files(task, candidate)
                if label != "starter":
                    shutil.copytree(task.root / "reference", candidate, dirs_exist_ok=True)
                if label == "broken-atomicity":
                    source = candidate / "src/Domain/ReservationStore.Rescheduling.cs"
                    source.write_text(source.read_text().replace(
                        "            var candidate = original with", "            reservations.Remove(id);\n            var candidate = original with"),
                        encoding="utf-8")
                elif label == "broken-old-contract":
                    source = candidate / "src/Domain/ReservationStore.cs"
                    source.write_text(source.read_text().replace("return CreateResult.DuplicateId;", "return CreateResult.Created;"),
                                      encoding="utf-8")
                snapshot = capture_project(task, candidate, root)
                result = runner.evaluate(task, ExtractedCode(None, ()), artifact_dir=root,
                                         llm_response_time_seconds=0, llm_usage=LlmUsage(), project_snapshot=snapshot)
                score = score_task(task, result)
                diagnostic = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.log"))
                if label == "starter":
                    self.assertEqual(score.feature_ratio, 0, diagnostic)
                    self.assertEqual(score.regression_ratio, 1, diagnostic)
                elif label == "reference":
                    self.assertEqual(score.feature_ratio, 1, diagnostic)
                    self.assertEqual(score.regression_ratio, 1, diagnostic)
                elif label == "broken-atomicity":
                    self.assertLess(score.feature_ratio, 1, diagnostic)
                    self.assertEqual(score.regression_ratio, 1, diagnostic)
                    self.assertIn("conflicting_reschedule_preserves_original", result.failed_tests)
                else:
                    self.assertEqual(score.feature_ratio, 1, diagnostic)
                    self.assertLess(score.regression_ratio, 1, diagnostic)
                    self.assertIn("existing_duplicate_ids_are_rejected", result.failed_tests)
                print(f"reservations {label}: feature={score.feature_ratio:.0%}, "
                      f"regression={score.regression_ratio:.0%}, score={score_benchmark([score]).final_score}", flush=True)


if __name__ == "__main__":
    unittest.main()
