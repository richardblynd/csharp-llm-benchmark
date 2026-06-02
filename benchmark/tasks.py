from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from benchmark.simple_yaml import load_yaml

DEFAULT_DIFFICULTY_ORDER = ("easy", "medium", "hard")


@dataclass(frozen=True)
class ScoreConfig:
    compile: float
    tests: dict[str, float]

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

    @property
    def prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")


def load_tasks(
    difficulty: str | None = None,
    *,
    tasks_root: Path = Path("tasks"),
) -> list[Task]:
    if _is_all_difficulties(difficulty):
        tasks: list[Task] = []
        for difficulty_name in _discover_difficulties(tasks_root):
            tasks.extend(_load_tasks_from_difficulty(difficulty_name, tasks_root))
        return tasks

    return _load_tasks_from_difficulty(str(difficulty), tasks_root)


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

    discovered = {path.name for path in tasks_root.iterdir() if path.is_dir()}
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
    return errors


def _load_task(task_dir: Path, data: dict[str, Any]) -> Task:
    score_data = data.get("score", {})
    tests_data = score_data.get("tests", {})
    if not isinstance(tests_data, dict):
        raise ValueError(f"{task_dir}: score.tests must be a mapping")

    return Task(
        id=str(data["id"]),
        name=str(data["name"]),
        difficulty=str(data["difficulty"]),
        root=task_dir,
        prompt_path=task_dir / "prompt.md",
        template_dir=task_dir / "template",
        tests_dir=task_dir / "tests",
        score=ScoreConfig(
            compile=float(score_data.get("compile", 0)),
            tests={str(key): float(value) for key, value in tests_data.items()},
        ),
        language=str(data.get("language", "csharp")),
        dotnet_version=str(data.get("dotnet_version", "8")),
        project_type=str(data.get("project_type", "classlib")),
        generated_file=str(data.get("generated_file", "Solution.cs")),
        solution_class=str(data.get("solution_class", "Solution")),
        solution_method=str(data.get("solution_method", "Execute")),
        public_files=tuple(data.get("public_files", [])),
        hidden_tests=tuple(data.get("hidden_tests", [])),
        build_command=str(data["build_command"]),
        test_command=str(data["test_command"]),
    )
