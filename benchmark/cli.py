from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

from benchmark.config import apply_cli_overrides, load_config
from benchmark.llm_client import (
    ExtractedCode,
    LlmClient,
    LlmUsage,
    extract_solution_code,
)
from benchmark.report import (
    create_run_dir,
    find_highest_token_task,
    format_duration_hms,
    write_summary,
)
from benchmark.runner import DockerRunner, TaskRunResult, write_result_json
from benchmark.scorer import TaskScore, score_benchmark, score_task
from benchmark.tasks import Task, load_tasks, validate_tasks


RUNNING_ICON = "⏳"
LLM_RUNNING_STATUS = f"{RUNNING_ICON} running"
TESTS_RUNNING_STATUS = f"{RUNNING_ICON} running unit tests"


@dataclass(frozen=True)
class PendingEvaluation:
    index: int
    task: Task
    task_dir: Path


@dataclass(frozen=True)
class PendingGeneration:
    index: int
    task: Task
    task_dir: Path


@dataclass(frozen=True)
class GeneratedSolution:
    extracted: ExtractedCode
    llm_response_time_seconds: float
    llm_usage: LlmUsage


@dataclass
class DashboardRow:
    task: Task
    llm: str = "waiting"
    tokens: str = ""
    evaluation: str = ""


@dataclass
class DashboardRenderer:
    rows: list[DashboardRow]
    header_lines: list[str]
    lines_rendered: int = 0
    rendered_once: bool = False
    can_redraw: bool = field(default_factory=lambda: sys.stdout.isatty())

    def render(self) -> None:
        lines = self._render_lines()
        if self.rendered_once and self.can_redraw:
            if len(lines) >= shutil.get_terminal_size(fallback=(80, 24)).lines:
                sys.stdout.write("\033[H\033[2J\033[3J")
            else:
                sys.stdout.write(f"\033[{self.lines_rendered}F\033[J")
        elif self.rendered_once:
            sys.stdout.write("\n")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self.lines_rendered = len(lines)
        self.rendered_once = True

    def _render_lines(self) -> list[str]:
        lines = [*self.header_lines, "", "Tasks:"]
        for row in self.rows:
            lines.extend(
                [
                    f"Task {row.task.id}: {row.task.name}",
                    f"  LLM: {row.llm}",
                    f"  Tokens: {row.tokens}",
                    f"  Evaluation: {row.evaluation}",
                ]
            )
        return lines


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-tasks":
            return _list_tasks(args)
        if args.command == "validate":
            return _validate(args)
        if args.command == "run":
            return _run(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m benchmark.cli")
    subparsers = parser.add_subparsers(dest="command")

    list_tasks = subparsers.add_parser("list-tasks", help="List benchmark tasks")
    list_tasks.add_argument(
        "--difficulty",
        help="Task difficulty to list. Omit or use 'all' to list every difficulty.",
    )

    validate = subparsers.add_parser("validate", help="Validate task metadata")
    validate.add_argument(
        "--difficulty",
        help=(
            "Task difficulty to validate. Omit or use 'all' to validate every "
            "difficulty."
        ),
    )

    run = subparsers.add_parser("run", help="Run the benchmark")
    run.add_argument("--config", type=Path, default=Path("config.example.yaml"))
    run.add_argument(
        "--difficulty",
        help=(
            "Task difficulty to run. Omit from both CLI and config, or use "
            "'all', to run every difficulty."
        ),
    )
    run.add_argument("--output-dir")
    run.add_argument("--base-url")
    run.add_argument("--api-key")
    run.add_argument("--model")
    run.add_argument("--task-id", help="Run only one task by id, e.g. easy-001")
    run.add_argument(
        "--resume",
        metavar="TASK_ID",
        help=(
            "Continue an existing run from this task id, reusing prior "
            "result.json files from the selected results folder."
        ),
    )
    run.add_argument(
        "--resume-dir",
        type=Path,
        help=(
            "Existing results folder to continue. If omitted with --resume, "
            "the runner prompts for a folder under the configured output dir."
        ),
    )
    run.add_argument(
        "--evaluation-workers",
        type=int,
        help=(
            "Number of Docker evaluations to run in parallel while new tasks are "
            "generated."
        ),
    )

    return parser


def _list_tasks(args: argparse.Namespace) -> int:
    for task in load_tasks(args.difficulty):
        print(f"{task.id}\t{task.name}\t{task.score.available_points:g} points")
    return 0


def _validate(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.difficulty)
    errors = validate_tasks(tasks)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Validated {len(tasks)} task(s) {_format_difficulty(args.difficulty)}.")
    return 0


def _run(args: argparse.Namespace) -> int:
    config = apply_cli_overrides(
        load_config(args.config),
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        difficulty=args.difficulty,
        output_dir=args.output_dir,
        task_id=args.task_id,
        evaluation_workers=args.evaluation_workers,
    )
    if args.resume is None and args.resume_dir is not None:
        raise ValueError("--resume-dir requires --resume")
    if args.resume is not None and config.benchmark.task_id is not None:
        raise ValueError("--resume cannot be combined with --task-id")

    tasks = load_tasks(config.benchmark.difficulty)
    tasks = _filter_tasks(tasks, config.benchmark.task_id)
    errors = validate_tasks(tasks)
    if errors:
        raise RuntimeError("Task validation failed:\n" + "\n".join(errors))

    resume_from_index = 0
    if args.resume is not None:
        resume_from_index = _find_task_index(tasks, args.resume)
        run_dir = _resolve_resume_run_dir(
            config.benchmark.output_dir,
            args.resume_dir,
        )
    else:
        run_dir = create_run_dir(
            config.benchmark.output_dir,
            model=config.llm.model,
            quantization=config.llm.quantization,
        )

    client = LlmClient(config.llm)
    runner = DockerRunner(config.docker)
    task_scores: list[TaskScore | None] = [None] * len(tasks)
    dashboard_rows = [DashboardRow(task) for task in tasks]
    header_lines = [
        f"Run directory: {run_dir}",
        f"Evaluation workers: {config.benchmark.evaluation_workers}",
    ]
    if args.resume is not None:
        _load_resumed_task_scores(
            tasks,
            task_scores,
            dashboard_rows,
            run_dir,
            resume_from_index=resume_from_index,
        )
        header_lines.extend(
            [
                f"Resume from: {args.resume}",
                f"Reused completed tasks: {resume_from_index}",
            ]
        )
    dashboard = DashboardRenderer(
        dashboard_rows,
        header_lines=header_lines,
    )
    next_task_index = resume_from_index
    pending_generation: Future[GeneratedSolution] | None = None
    current_generation: PendingGeneration | None = None
    pending: dict[Future[TaskRunResult], PendingEvaluation] = {}

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="benchmark-llm",
    ) as generation_executor, ThreadPoolExecutor(
        max_workers=config.benchmark.evaluation_workers,
        thread_name_prefix="benchmark-eval",
    ) as evaluation_executor:
        if next_task_index < len(tasks):
            pending_generation, current_generation = _queue_generation(
                generation_executor,
                client,
                tasks[next_task_index],
                run_dir,
                index=next_task_index,
            )
            dashboard_rows[next_task_index].llm = LLM_RUNNING_STATUS
            next_task_index += 1
        dashboard.render()

        while pending_generation is not None or pending:
            active_futures: set[Future] = set(pending)
            if pending_generation is not None:
                active_futures.add(pending_generation)

            completed_futures, _ = wait(
                active_futures,
                return_when=FIRST_COMPLETED,
            )

            if (
                pending_generation is not None
                and pending_generation in completed_futures
                and current_generation is not None
            ):
                generated = pending_generation.result()
                row = dashboard_rows[current_generation.index]
                row.llm = f"{generated.llm_response_time_seconds:.2f}s"
                row.tokens = _format_tokens(generated.llm_usage.total_tokens)
                row.evaluation = TESTS_RUNNING_STATUS
                evaluation_future = evaluation_executor.submit(
                    runner.evaluate,
                    current_generation.task,
                    generated.extracted,
                    artifact_dir=current_generation.task_dir,
                    llm_response_time_seconds=generated.llm_response_time_seconds,
                    llm_usage=generated.llm_usage,
                )
                pending[evaluation_future] = PendingEvaluation(
                    current_generation.index,
                    current_generation.task,
                    current_generation.task_dir,
                )
                _refresh_evaluation_statuses(
                    pending,
                    dashboard_rows,
                    config.benchmark.evaluation_workers,
                )
                pending_generation = None
                current_generation = None

                if next_task_index < len(tasks):
                    pending_generation, current_generation = _queue_generation(
                        generation_executor,
                        client,
                        tasks[next_task_index],
                        run_dir,
                        index=next_task_index,
                    )
                    dashboard_rows[next_task_index].llm = LLM_RUNNING_STATUS
                    next_task_index += 1
                dashboard.render()

            for completed_future in completed_futures:
                if completed_future not in pending:
                    continue
                pending_evaluation = pending.pop(completed_future)
                result = completed_future.result()
                write_result_json(pending_evaluation.task_dir / "result.json", result)
                task_score = score_task(pending_evaluation.task, result)
                task_scores[pending_evaluation.index] = task_score
                dashboard_rows[pending_evaluation.index].evaluation = (
                    _format_evaluation_status(
                        pending_evaluation.task,
                        result,
                        task_score,
                    )
                )
                _refresh_evaluation_statuses(
                    pending,
                    dashboard_rows,
                    config.benchmark.evaluation_workers,
                )
                dashboard.render()

    completed_task_scores = _completed_task_scores(task_scores)
    benchmark_score = score_benchmark(completed_task_scores)
    write_summary(
        run_dir,
        config=config,
        score=benchmark_score,
        task_scores=completed_task_scores,
    )
    print(
        f"Final score: {benchmark_score.final_score} "
        f"({benchmark_score.earned_points:g}/{benchmark_score.available_points:g})"
    )
    total_llm_time = sum(
        task_score.llm_response_time_seconds for task_score in completed_task_scores
    )
    print(f"Total LLM response time: {format_duration_hms(total_llm_time)}")
    total_llm_tokens = _sum_known_tokens(
        task_score.llm_usage.total_tokens for task_score in completed_task_scores
    )
    print(f"Total LLM tokens: {_format_tokens(total_llm_tokens)}")
    highest_token_task = find_highest_token_task(completed_task_scores)
    if highest_token_task is None:
        print("Highest-token task: unavailable (token usage unavailable for all tasks)")
    else:
        print(
            "Highest-token task: "
            f"{highest_token_task.task_id} "
            f"({_format_tokens(highest_token_task.llm_usage.total_tokens)}, "
            f"LLM time: {highest_token_task.llm_response_time_seconds:.2f}s)"
        )
    return 0


def _queue_generation(
    executor: ThreadPoolExecutor,
    client: LlmClient,
    task: Task,
    run_dir: Path,
    *,
    index: int,
) -> tuple[Future[GeneratedSolution], PendingGeneration]:
    task_dir = run_dir / "tasks" / task.id
    task_dir.mkdir(parents=True, exist_ok=True)
    pending_generation = PendingGeneration(index, task, task_dir)
    return executor.submit(_generate_solution, client, task, task_dir), pending_generation


def _generate_solution(
    client: LlmClient,
    task: Task,
    task_dir: Path,
) -> GeneratedSolution:
    prompt = task.prompt
    (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    llm_response = client.complete(prompt)
    (task_dir / "response.md").write_text(llm_response.content, encoding="utf-8")
    required_public_class = task.solution_class if task.difficulty == "easy" else None
    extracted = extract_solution_code(
        llm_response.content,
        required_public_class=required_public_class,
    )
    if extracted.code is not None:
        generated_path = task_dir / task.generated_file
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text(extracted.code, encoding="utf-8")

    return GeneratedSolution(
        extracted=extracted,
        llm_response_time_seconds=llm_response.response_time_seconds,
        llm_usage=llm_response.usage,
    )


def _completed_task_scores(task_scores: list[TaskScore | None]) -> list[TaskScore]:
    completed = [task_score for task_score in task_scores if task_score is not None]
    if len(completed) != len(task_scores):
        raise RuntimeError("Some task evaluations did not complete.")
    return completed


def _load_resumed_task_scores(
    tasks: list[Task],
    task_scores: list[TaskScore | None],
    dashboard_rows: list[DashboardRow],
    run_dir: Path,
    *,
    resume_from_index: int,
) -> None:
    missing: list[str] = []
    for index, task in enumerate(tasks[:resume_from_index]):
        result_path = run_dir / "tasks" / task.id / "result.json"
        if not result_path.exists():
            missing.append(task.id)
            continue

        result = _read_task_result_json(result_path)
        if result.task_id != task.id:
            raise ValueError(
                f"{result_path} belongs to {result.task_id}, expected {task.id}"
            )

        task_score = score_task(task, result)
        task_scores[index] = task_score
        dashboard_rows[index].llm = f"{task_score.llm_response_time_seconds:.2f}s"
        dashboard_rows[index].tokens = _format_tokens(
            task_score.llm_usage.total_tokens
        )
        dashboard_rows[index].evaluation = (
            "resumed "
            + _format_evaluation_status(
                task,
                result,
                task_score,
            )
        )

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Cannot resume because prior result.json files are missing for: "
            f"{joined}"
        )


def _read_task_result_json(path: Path) -> TaskRunResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "status" not in data:
        raise ValueError(f"{path} is missing status")

    llm_usage_data = data.get("llm_usage") or {}
    if not isinstance(llm_usage_data, dict):
        llm_usage_data = {}

    return TaskRunResult(
        task_id=str(data.get("task_id") or path.parent.name),
        status=str(data["status"]),
        llm_response_time_seconds=float(data.get("llm_response_time_seconds") or 0),
        llm_usage=LlmUsage(
            prompt_tokens=_optional_int(llm_usage_data.get("prompt_tokens")),
            completion_tokens=_optional_int(
                llm_usage_data.get("completion_tokens")
            ),
            total_tokens=_optional_int(llm_usage_data.get("total_tokens")),
            reasoning_tokens=_optional_int(llm_usage_data.get("reasoning_tokens")),
        ),
        workdir=_optional_text(data.get("workdir")),
        build=None,
        test=None,
        passed_tests=_string_tuple(data.get("passed_tests")),
        failed_tests=_string_tuple(data.get("failed_tests")),
        extraction_warnings=_string_tuple(data.get("extraction_warnings")),
        extraction_error=_optional_text(data.get("extraction_error")),
        infrastructure_error=_optional_text(data.get("infrastructure_error")),
    )


def _resolve_resume_run_dir(output_dir: Path, resume_dir: Path | None) -> Path:
    if resume_dir is None:
        run_dir = _prompt_for_resume_run_dir(output_dir)
    else:
        run_dir = _normalize_resume_run_dir(output_dir, resume_dir)

    if not run_dir.is_dir():
        raise FileNotFoundError(f"Results folder not found: {run_dir}")
    if not (run_dir / "tasks").is_dir():
        raise FileNotFoundError(f"Results folder has no tasks directory: {run_dir}")
    return run_dir


def _prompt_for_resume_run_dir(output_dir: Path) -> Path:
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    candidates = sorted(
        (
            path
            for path in output_dir.iterdir()
            if path.is_dir() and (path / "tasks").is_dir()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No results folders found under {output_dir}")

    if not sys.stdin.isatty():
        available = ", ".join(path.name for path in candidates[:10])
        raise RuntimeError(
            "--resume requires --resume-dir when stdin is not interactive. "
            f"Available folders: {available}"
        )

    print("Available results folders:")
    for index, path in enumerate(candidates, start=1):
        print(f"  {index}. {path.name}")
    choice = input("Choose results folder to resume [1]: ").strip()
    if not choice:
        return candidates[0]
    if choice.isdecimal():
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(candidates):
            return candidates[selected_index]
        raise ValueError(f"Invalid results folder selection: {choice}")
    return _normalize_resume_run_dir(output_dir, Path(choice))


def _normalize_resume_run_dir(output_dir: Path, resume_dir: Path) -> Path:
    if resume_dir.is_absolute():
        return resume_dir
    if resume_dir.exists():
        return resume_dir
    return output_dir / resume_dir


def _refresh_evaluation_statuses(
    pending_evaluations: dict[Future[TaskRunResult], PendingEvaluation],
    rows: list[DashboardRow],
    evaluation_workers: int,
) -> None:
    for position, pending in enumerate(
        sorted(
            pending_evaluations.values(),
            key=lambda pending: pending.index,
        )
    ):
        rows[pending.index].evaluation = (
            TESTS_RUNNING_STATUS
            if position < evaluation_workers
            else "waiting unit tests"
        )


def _format_evaluation_status(
    task: Task,
    result: TaskRunResult,
    task_score: TaskScore,
) -> str:
    label = {
        "passed": "passed",
        "tests_failed": "failed",
        "build_failed": "build failed",
        "extraction_error": "extraction error",
        "infrastructure_error": "infrastructure error",
    }.get(result.status, result.status)
    total_tests = len(task.score.tests)
    if total_tests:
        passed_tests = sum(
            1
            for test_name in task.score.tests
            if test_name in task_score.passed_tests
        )
        return f"{label} ({passed_tests}/{total_tests})"
    return label


def _find_task_index(tasks: list[Task], task_id: str) -> int:
    for index, task in enumerate(tasks):
        if task.id == task_id:
            return index
    available = ", ".join(task.id for task in tasks)
    raise ValueError(f"Task id not found: {task_id}. Available ids: {available}")


def _filter_tasks(tasks, task_id: str | None):
    if task_id is None:
        return tasks
    matches = [task for task in tasks if task.id == task_id]
    if matches:
        return matches
    available = ", ".join(task.id for task in tasks)
    raise ValueError(f"Task id not found: {task_id}. Available ids: {available}")


def _format_difficulty(difficulty: str | None) -> str:
    if difficulty is None or difficulty.strip().lower() == "all":
        return "across all difficulties"
    return f"for difficulty '{difficulty}'"


def _sum_known_tokens(values) -> int | None:
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None
    return sum(known_values)


def _optional_int(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_tuple(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _format_tokens(tokens: int | None) -> str:
    if tokens is None:
        return "tokens unavailable"
    return f"{tokens} tokens"


if __name__ == "__main__":
    raise SystemExit(main())
