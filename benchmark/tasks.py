from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any

from benchmark.simple_yaml import load_yaml
from benchmark.workspace import relative_path

DEFAULT_DIFFICULTY_ORDER = ("easy", "medium", "hard")
SUPPORTED_SUITES = ("greenfield", "evolution")

# Fixed set of 7 tasks used for temperature discovery. Covers 7 skill categories:
# basic parsing/aggregation, generics/data structures, async/parallelism,
# Web API + domain logic, SOLID/OOP patterns, advanced APIs with concurrency,
# and composable expression design.
DISCOVERY_TASK_IDS = (
    "easy-003",
    "easy-006",
    "medium-006",   # parallel-executor (bounded concurrency + cancellation)
    "medium-009",   # room-reservations-api
    "medium-011",   # srp-reporting
    "hard-007",
    "hard-013",
)

EVOLUTION_DISCOVERY_TASK_IDS = (
    "evolution-discovery-easy-001",
    "evolution-discovery-medium-001",
    "evolution-discovery-medium-002",
    "evolution-discovery-hard-001",
)

DISCOVERY_TASK_DESCRIPTIONS = {
    "easy-003": ("Basic", "Parsing + dictionary + category aggregation"),
    "easy-006": ("Generics/Type", "Generic data structure with internal state"),
    "medium-006": ("Async/Parallel", "Bounded parallel execution with cancellation"),
    "medium-009": ("Web API", "ASP.NET Core + interval conflict detection"),
    "medium-011": ("SOLID/OOP", "SRP separation of concerns"),
    "hard-007": ("Advanced Web API", "Idempotency + thread safety"),
    "hard-013": ("Advanced Design", "Composable generic expression trees"),
}


@dataclass(frozen=True)
class ScoreConfig:
    compile: float
    tests: dict[str, float]
    regression: dict[str, float] = field(default_factory=dict)

    @property
    def available_points(self) -> float:
        return self.compile + sum(self.tests.values())


@dataclass(frozen=True)
class Task:
    id: str
    name: str
    difficulty: str
    root: Path
    prompt_path: Path
    template_dir: Path
    tests_dir: Path
    score: ScoreConfig
    language: str
    dotnet_version: str
    project_type: str
    generated_file: str
    solution_class: str
    solution_method: str
    public_files: tuple[str, ...]
    hidden_tests: tuple[str, ...]
    build_command: str
    test_command: str
    suite: str = "greenfield"
    role: str = "scored"
    version: str = "1"
    editable_files: tuple[str, ...] = ()
    build_project: str | None = None
    test_groups: tuple[TestGroup, ...] = ()

    @property
    def prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class TestGroup:
    name: str
    build_command: str
    test_command: str


def load_tasks(
    difficulty: str | None = None,
    *,
    tasks_root: Path = Path("tasks"),
    suite: str = "greenfield",
    role: str | None = "scored",
) -> list[Task]:
    tasks_root = tasks_root.resolve()
    if suite == "all":
        return [task for selected_suite in SUPPORTED_SUITES
                for task in load_tasks(difficulty, tasks_root=tasks_root,
                                       suite=selected_suite, role=role)]
    if suite not in SUPPORTED_SUITES:
        raise ValueError(f"Unknown task suite: {suite}")
    if suite == "evolution":
        tasks_root = tasks_root / "evolution"
    if _is_all_difficulties(difficulty):
        tasks: list[Task] = []
        for difficulty_name in _discover_difficulties(tasks_root):
            tasks.extend(_load_tasks_from_difficulty(difficulty_name, tasks_root))
        return [task for task in tasks if role is None or task.role == role]

    return [task for task in _load_tasks_from_difficulty(str(difficulty), tasks_root)
            if role is None or task.role == role]


def _load_tasks_from_difficulty(
    difficulty: str,
    tasks_root: Path,
) -> list[Task]:
    difficulty_dir = tasks_root / difficulty
    if not difficulty_dir.exists():
        raise FileNotFoundError(f"Task difficulty directory not found: {difficulty_dir}")

    tasks: list[Task] = []
    for task_dir in sorted(path for path in difficulty_dir.iterdir() if path.is_dir()):
        task_file = task_dir / "task.yaml"
        if not task_file.exists():
            continue
        tasks.append(_load_task(task_dir, load_yaml(task_file)))
    return tasks


def _is_all_difficulties(difficulty: str | None) -> bool:
    return difficulty is None or difficulty.strip().lower() == "all"


def _discover_difficulties(tasks_root: Path) -> tuple[str, ...]:
    if not tasks_root.exists():
        raise FileNotFoundError(f"Task root directory not found: {tasks_root}")

    discovered = {path.name for path in tasks_root.iterdir()
                  if path.is_dir() and path.name not in SUPPORTED_SUITES}
    ordered = [
        difficulty for difficulty in DEFAULT_DIFFICULTY_ORDER if difficulty in discovered
    ]
    ordered.extend(sorted(discovered - set(DEFAULT_DIFFICULTY_ORDER)))
    return tuple(ordered)


def validate_tasks(tasks: list[Task]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for task in tasks:
        if task.id in seen_ids:
            errors.append(f"Duplicate task id: {task.id}")
        seen_ids.add(task.id)

        if not task.prompt_path.exists():
            errors.append(f"{task.id}: missing prompt.md")
        if not task.template_dir.exists():
            errors.append(f"{task.id}: missing template directory")
        if not task.tests_dir.exists():
            errors.append(f"{task.id}: missing tests directory")
        for public_file in task.public_files:
            if not (task.template_dir / public_file).exists():
                errors.append(f"{task.id}: missing template file {public_file}")
        for hidden_test in task.hidden_tests:
            if not (task.tests_dir / hidden_test).exists():
                errors.append(f"{task.id}: missing hidden test file {hidden_test}")
        if task.score.available_points <= 0:
            errors.append(f"{task.id}: score must be positive")
        if task.suite not in SUPPORTED_SUITES or task.role not in {"scored", "discovery"}:
            errors.append(f"{task.id}: invalid suite or role")
        for path in (*task.public_files, *task.hidden_tests):
            try:
                relative_path(path)
            except ValueError as exc:
                errors.append(f"{task.id}: {exc}")
        if task.suite == "evolution":
            if not task.editable_files or task.build_project not in task.public_files:
                errors.append(f"{task.id}: evolution requires editable_files and a public build_project")
            if {group.name for group in task.test_groups} != {"feature", "regression"} or len(task.test_groups) != 2:
                errors.append(f"{task.id}: evolution requires feature and regression test groups")
            if task.score.compile != 0 or not task.score.tests or not task.score.regression:
                errors.append(f"{task.id}: evolution requires feature/regression weights and zero compile points")
            if task.score.tests.keys() & task.score.regression.keys():
                errors.append(f"{task.id}: test names must be unique across groups")
        weights = [task.score.compile, *task.score.tests.values(), *task.score.regression.values()]
        if any(not math.isfinite(weight) or weight < 0 for weight in weights):
            errors.append(f"{task.id}: score weights must be finite and nonnegative")
        if any(weight <= 0 for weight in (*task.score.tests.values(), *task.score.regression.values())):
            errors.append(f"{task.id}: test weights must be positive")
    return errors


def select_discovery_tasks(tasks: list[Task]) -> list[Task]:
    """Select the fixed set of discovery tasks from the loaded task list.

    Raises RuntimeError if any expected discovery task is missing.
    Preserves the order defined in DISCOVERY_TASK_IDS (easy → medium → hard).
    """
    task_by_id = {task.id: task for task in tasks}
    selected: list[Task] = []
    missing: list[str] = []

    suites = {task.suite for task in tasks}
    expected_ids = EVOLUTION_DISCOVERY_TASK_IDS if suites == {"evolution"} else DISCOVERY_TASK_IDS
    for expected_id in expected_ids:
        if expected_id in task_by_id:
            selected.append(task_by_id[expected_id])
        else:
            missing.append(expected_id)

    if missing:
        available_ids = ", ".join(task.id for task in tasks)
        raise RuntimeError(
            f"Discovery tasks not found: {', '.join(missing)}. "
            f"Available ids: {available_ids}"
        )
    return selected


def _load_task(task_dir: Path, data: dict[str, Any]) -> Task:
    score_data = data.get("score", {})
    tests_data = score_data.get("tests", {})
    if not isinstance(tests_data, dict):
        raise ValueError(f"{task_dir}: score.tests must be a mapping")
    suite = str(data.get("suite", "greenfield"))
    groups = data.get("test_groups", {})

    return Task(
        id=str(data["id"]),
        name=str(data["name"]),
        difficulty=str(data["difficulty"]),
        root=task_dir,
        prompt_path=task_dir / "prompt.md",
        template_dir=task_dir / ("starter" if suite == "evolution" else "template"),
        tests_dir=task_dir / "tests",
        score=ScoreConfig(
            compile=float(score_data.get("compile", 0)),
            tests={str(key): float(value) for key, value in tests_data.items()},
            regression={str(key): float(value) for key, value in score_data.get("regression", {}).items()},
        ),
        language=str(data.get("language", "csharp")),
        dotnet_version=str(data.get("dotnet_version", "8")),
        project_type=str(data.get("project_type", "classlib")),
        generated_file=str(data.get("generated_file", "" if suite == "evolution" else "Solution.cs")),
        solution_class=str(data.get("solution_class", "Solution")),
        solution_method=str(data.get("solution_method", "Execute")),
        public_files=tuple(data.get("public_files", [])),
        hidden_tests=tuple(data.get("hidden_tests", [])),
        build_command=str(data["build_command"]),
        test_command=str(data.get("test_command", "")),
        suite=suite,
        role=str(data.get("role", "scored")),
        version=str(data.get("version", "1")),
        editable_files=tuple(data.get("editable_files", [])),
        build_project=data.get("build_project"),
        test_groups=tuple(TestGroup(str(name), str(group["build_command"]), str(group["test_command"]))
                          for name, group in groups.items()),
    )
