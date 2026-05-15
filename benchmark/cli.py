from __future__ import annotations

import argparse
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
    tasks = load_tasks(config.benchmark.difficulty)
    tasks = _filter_tasks(tasks, config.benchmark.task_id)
    errors = validate_tasks(tasks)
    if errors:
        raise RuntimeError("Task validation failed:\n" + "\n".join(errors))

    run_dir = create_run_dir(config.benchmark.output_dir)
    client = LlmClient(config.llm)
    runner = DockerRunner(config.docker)
    task_scores: list[TaskScore | None] = [None] * len(tasks)
    dashboard_rows = [DashboardRow(task) for task in tasks]
    dashboard = DashboardRenderer(
        dashboard_rows,
        header_lines=[
            f"Run directory: {run_dir}",
            f"Evaluation workers: {config.benchmark.evaluation_workers}",
        ],
    )
    next_task_index = 0
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
        if tasks:
            pending_generation, current_generation = _queue_generation(
                generation_executor,
                client,
                tasks[0],
                run_dir,
                index=0,
            )
            dashboard_rows[0].llm = LLM_RUNNING_STATUS
            next_task_index = 1
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


def _format_tokens(tokens: int | None) -> str:
    if tokens is None:
        return "tokens unavailable"
    return f"{tokens} tokens"


if __name__ == "__main__":
    raise SystemExit(main())
