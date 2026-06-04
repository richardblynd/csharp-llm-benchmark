from __future__ import annotations

import argparse
import json
import shutil
import sys
import unicodedata
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace
from pathlib import Path

from benchmark.config import apply_cli_overrides, load_config, with_llm_temperature
from benchmark.generation import (
    GeneratedSolution,
    OpenCodeGenerator,
    PreparedOpenCodeGeneration,
    SolutionGenerator,
    create_solution_generator,
    opencode_metadata_to_dict,
)
from benchmark.llm_client import LlmUsage
from benchmark.report import (
    create_run_dir,
    find_highest_token_task,
    format_duration_hms,
    write_summary,
)
from benchmark.runner import DockerRunner, TaskRunResult, write_result_json
from benchmark.scorer import BenchmarkScore, TaskScore, score_benchmark, score_task
from benchmark.tasks import Task, load_tasks, validate_tasks


RUNNING_ICON = "⏳"
LLM_RUNNING_STATUS = f"{RUNNING_ICON} running"
TESTS_RUNNING_STATUS = f"{RUNNING_ICON} running unit tests"


@dataclass(frozen=True)
class PendingEvaluation:
    row_index: int
    task_index: int
    temperature_index: int
    temperature: float
    task: Task
    task_dir: Path


@dataclass(frozen=True)
class PendingGeneration:
    row_index: int
    task_index: int
    temperature_index: int
    temperature: float
    task: Task
    task_dir: Path


@dataclass(frozen=True)
class ReadyGeneration:
    pending: PendingGeneration
    generator: OpenCodeGenerator
    prepared: PreparedOpenCodeGeneration


@dataclass(frozen=True)
class TemperatureRun:
    temperature: float
    score: BenchmarkScore
    task_scores: list[TaskScore]


@dataclass
class DashboardRow:
    task: Task
    temperature: float | None = None
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
        terminal_width = shutil.get_terminal_size(fallback=(120, 24)).columns
        return [*self.header_lines, "", "Tasks:", *_render_dashboard_table(
            self.rows,
            terminal_width=terminal_width,
        )]


def _render_dashboard_table(
    rows: list[DashboardRow],
    *,
    terminal_width: int,
) -> list[str]:
    columns = [
        ("Task", [_dashboard_task_label(row) for row in rows], 6, 18, "left"),
        ("Name", [row.task.name for row in rows], 12, 34, "left"),
        ("LLM", [row.llm for row in rows], 14, 32, "left"),
        ("Tokens", [row.tokens for row in rows], 16, 20, "right"),
        ("Evaluation", [row.evaluation for row in rows], 26, 48, "left"),
    ]
    widths = _fit_table_widths(
        [
            min(
                max(
                    _terminal_text_width(header),
                    *(_terminal_text_width(value) for value in values),
                ),
                maximum,
            )
            for header, values, _minimum, maximum, _align in columns
        ],
        minimums=[minimum for _header, _values, minimum, _maximum, _align in columns],
        terminal_width=terminal_width,
    )
    headers = [header for header, _values, _minimum, _maximum, _align in columns]
    alignments = [align for _header, _values, _minimum, _maximum, align in columns]
    separator = _format_table_separator(widths)
    lines = [
        separator,
        _format_table_row(headers, widths, alignments),
        separator,
    ]
    for row in rows:
        lines.append(
            _format_table_row(
                [
                    _dashboard_task_label(row),
                    row.task.name,
                    row.llm,
                    row.tokens,
                    row.evaluation,
                ],
                widths,
                alignments,
            )
        )
    lines.append(separator)
    return lines


def _dashboard_task_label(row: DashboardRow) -> str:
    if row.temperature is None:
        return row.task.id
    return f"{row.task.id} @ {_format_temperature(row.temperature)}"


def _fit_table_widths(
    desired_widths: list[int],
    *,
    minimums: list[int],
    terminal_width: int,
) -> list[int]:
    table_padding = 3 * len(desired_widths) + 1
    available_width = max(sum(minimums), terminal_width - table_padding)
    widths = [max(width, minimum) for width, minimum in zip(desired_widths, minimums)]
    while sum(widths) > available_width:
        candidates = [
            index
            for index, width in enumerate(widths)
            if width > minimums[index]
        ]
        if not candidates:
            break
        index = max(
            candidates,
            key=lambda candidate: widths[candidate] - minimums[candidate],
        )
        widths[index] -= 1
    return widths


def _format_table_separator(widths: list[int]) -> str:
    return "+" + "+".join("-" * (width + 2) for width in widths) + "+"


def _format_table_row(
    values: list[str],
    widths: list[int],
    alignments: list[str],
) -> str:
    cells = []
    for value, width, alignment in zip(values, widths, alignments):
        text = _truncate_table_cell(value, width)
        if alignment == "right":
            cells.append(" " + _pad_table_cell(text, width, alignment) + " ")
        else:
            cells.append(" " + _pad_table_cell(text, width, alignment) + " ")
    return "|" + "|".join(cells) + "|"


def _truncate_table_cell(value: str, width: int) -> str:
    if _terminal_text_width(value) <= width:
        return value
    if width <= 3:
        return _truncate_to_terminal_width(value, width)
    return _truncate_to_terminal_width(value, width - 3) + "..."


def _pad_table_cell(value: str, width: int, alignment: str) -> str:
    padding = max(width - _terminal_text_width(value), 0)
    if alignment == "right":
        return (" " * padding) + value
    return value + (" " * padding)


def _truncate_to_terminal_width(value: str, width: int) -> str:
    result: list[str] = []
    used_width = 0
    for character in value:
        character_width = _terminal_character_width(character)
        if used_width + character_width > width:
            break
        result.append(character)
        used_width += character_width
    return "".join(result)


def _terminal_text_width(value: str) -> int:
    return sum(_terminal_character_width(character) for character in value)


def _terminal_character_width(character: str) -> int:
    if unicodedata.combining(character):
        return 0
    if unicodedata.category(character) in {"Cf", "Mn", "Me"}:
        return 0
    if unicodedata.east_asian_width(character) in {"F", "W"}:
        return 2
    return 1


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
    run.add_argument("--model-label")
    run.add_argument("--company")
    run.add_argument(
        "--top-p",
        type=float,
        help=(
            "Optional LLM top_p sampling parameter. Omit to let the provider "
            "default apply."
        ),
    )
    run.add_argument(
        "--min-p",
        type=float,
        help=(
            "Optional LLM min_p sampling parameter. Omit to let the provider "
            "default apply."
        ),
    )
    run.add_argument(
        "--top-k",
        type=int,
        help=(
            "Optional LLM top_k sampling parameter. Omit to let the provider "
            "default apply."
        ),
    )
    run.add_argument(
        "--repetition-penalty",
        type=float,
        help=(
            "Optional LLM repetition_penalty sampling parameter. Omit to let "
            "the provider default apply."
        ),
    )
    run.add_argument(
        "--generator",
        choices=("llm", "opencode"),
        help="Solution generator to use. Defaults to benchmark.generator.",
    )
    run.add_argument(
        "--opencode-version",
        help="Pinned OpenCode package version to install for opencode runs.",
    )
    run.add_argument(
        "--opencode-timeout-seconds",
        type=int,
        help="Timeout for OpenCode install and session commands.",
    )
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
        model_label=args.model_label,
        company=args.company,
        difficulty=args.difficulty,
        output_dir=args.output_dir,
        task_id=args.task_id,
        evaluation_workers=args.evaluation_workers,
        generator=args.generator,
        opencode_version=args.opencode_version,
        opencode_timeout_seconds=args.opencode_timeout_seconds,
        top_p=args.top_p,
        min_p=args.min_p,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
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
            model_label=config.llm.effective_model_label,
            quantization=config.llm.quantization,
        )

    temperature_runs = _run_task_major_temperatures(
        config,
        tasks,
        run_dir=run_dir,
        resume_from_index=resume_from_index,
        resume_task_id=args.resume,
    )

    best_run = _select_best_temperature_run(temperature_runs)
    best_config = with_llm_temperature(config, best_run.temperature)
    write_summary(
        run_dir,
        config=best_config,
        score=best_run.score,
        task_scores=best_run.task_scores,
        temperature_scores=temperature_runs,
    )
    print(f"Best temperature: {_format_temperature(best_run.temperature)}")
    print(
        f"Final score: {best_run.score.final_score} "
        f"({best_run.score.earned_points:g}/{best_run.score.available_points:g})"
    )
    total_llm_time = sum(
        task_score.llm_response_time_seconds for task_score in best_run.task_scores
    )
    print(f"Total LLM response time: {format_duration_hms(total_llm_time)}")
    total_llm_tokens = _sum_known_tokens(
        task_score.llm_usage.total_tokens for task_score in best_run.task_scores
    )
    print(f"Total LLM tokens: {_format_tokens(total_llm_tokens)}")
    highest_token_task = find_highest_token_task(best_run.task_scores)
    if highest_token_task is None:
        print("Highest-token task: unavailable (token usage unavailable for all tasks)")
    else:
        print(
            "Highest-token task: "
            f"{highest_token_task.task_id} "
            f"({_format_tokens(highest_token_task.llm_usage.total_tokens)}, "
            f"LLM time: {highest_token_task.llm_response_time_seconds:.2f}s)"
        )
    if len(temperature_runs) > 1:
        print("Temperature scores:")
        for temperature_run in temperature_runs:
            print(
                "  "
                f"{_format_temperature(temperature_run.temperature)}: "
                f"{temperature_run.score.final_score} "
                f"({temperature_run.score.earned_points:g}/"
                f"{temperature_run.score.available_points:g})"
            )
    return 0


def _run_task_major_temperatures(
    config,
    tasks: list[Task],
    *,
    run_dir: Path,
    resume_from_index: int,
    resume_task_id: str | None,
) -> list[TemperatureRun]:
    temperatures = config.llm.temperatures
    multi_temperature = len(temperatures) > 1
    temperature_configs = [
        with_llm_temperature(config, temperature) for temperature in temperatures
    ]
    solution_generators = [
        create_solution_generator(temperature_config)
        for temperature_config in temperature_configs
    ]
    runner = DockerRunner(config.docker)
    task_scores_by_temperature: list[list[TaskScore | None]] = [
        [None] * len(tasks) for _temperature in temperatures
    ]
    dashboard_rows: list[DashboardRow] = []
    queued_generations: list[PendingGeneration] = []

    for task_index, task in enumerate(tasks):
        for temperature_index, temperature in enumerate(temperatures):
            row_index = len(dashboard_rows)
            dashboard_rows.append(DashboardRow(task, temperature=temperature))
            task_root_dir = _temperature_task_root(
                run_dir,
                temperature,
                multi_temperature=multi_temperature,
            )
            task_dir = task_root_dir / "tasks" / task.id
            result_path = task_dir / "result.json"
            if resume_task_id is not None and result_path.exists():
                _load_existing_task_score(
                    task,
                    result_path,
                    task_scores_by_temperature[temperature_index],
                    dashboard_rows,
                    task_index=task_index,
                    row_index=row_index,
                    expected_temperature=temperature,
                    prefix="resumed ",
                )
                continue
            if resume_task_id is not None and task_index < resume_from_index:
                raise RuntimeError(
                    "Cannot resume because a prior result.json file is missing for "
                    f"{task.id} at temperature {_format_temperature(temperature)}: "
                    f"{result_path}"
                )
            queued_generations.append(
                PendingGeneration(
                    row_index=row_index,
                    task_index=task_index,
                    temperature_index=temperature_index,
                    temperature=temperature,
                    task=task,
                    task_dir=task_dir,
                )
            )

    header_lines = [
        f"Run directory: {run_dir}",
        f"Generator: {config.benchmark.generator}",
        "Temperature order: task-major",
        f"Evaluation workers: {config.benchmark.evaluation_workers}",
    ]
    if multi_temperature:
        header_lines.append(
            "Configured temperatures: "
            + ", ".join(
                _format_temperature(temperature)
                for temperature in temperatures
            )
        )
    if config.benchmark.generator == "opencode":
        header_lines.append(f"OpenCode version: {config.opencode.version}")
        header_lines.append(
            "OpenCode prepare ahead: "
            + ("enabled" if config.opencode.prepare_ahead else "disabled")
        )
        if config.opencode.prepare_ahead:
            header_lines.append(
                "OpenCode precreate container: "
                + ("enabled" if config.opencode.precreate_container else "disabled")
            )
    if config.llm.requests_per_minute is not None:
        header_lines.append(
            f"LLM rate limit: {config.llm.requests_per_minute} requests/minute"
        )
    if resume_task_id is not None:
        header_lines.extend(
            [
                f"Resume from: {resume_task_id}",
                f"Queued missing task/temperature pairs: {len(queued_generations)}",
            ]
        )
    dashboard = DashboardRenderer(
        dashboard_rows,
        header_lines=header_lines,
    )
    if _can_prepare_opencode_ahead(config, solution_generators):
        _run_prepared_opencode_queue(
            config,
            runner,
            solution_generators,
            queued_generations,
            dashboard,
            dashboard_rows,
            task_scores_by_temperature,
        )
    else:
        _run_generation_queue(
            config,
            runner,
            solution_generators,
            queued_generations,
            dashboard,
            dashboard_rows,
            task_scores_by_temperature,
        )

    return [
        TemperatureRun(
            temperature=temperature,
            score=score_benchmark(completed_task_scores),
            task_scores=completed_task_scores,
        )
        for temperature, completed_task_scores in zip(
            temperatures,
            (
                _completed_task_scores(task_scores)
                for task_scores in task_scores_by_temperature
            ),
        )
    ]


def _can_prepare_opencode_ahead(
    config,
    solution_generators: list[SolutionGenerator],
) -> bool:
    return (
        config.benchmark.generator == "opencode"
        and config.opencode.prepare_ahead
        and all(
            isinstance(generator, OpenCodeGenerator)
            for generator in solution_generators
        )
    )


def _run_generation_queue(
    config,
    runner: DockerRunner,
    solution_generators: list[SolutionGenerator],
    queued_generations: list[PendingGeneration],
    dashboard: DashboardRenderer,
    dashboard_rows: list[DashboardRow],
    task_scores_by_temperature: list[list[TaskScore | None]],
) -> None:
    next_generation_index = 0
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
        if next_generation_index < len(queued_generations):
            pending_generation, current_generation = _queue_generation(
                generation_executor,
                solution_generators[
                    queued_generations[next_generation_index].temperature_index
                ],
                queued_generations[next_generation_index],
            )
            dashboard_rows[
                queued_generations[next_generation_index].row_index
            ].llm = LLM_RUNNING_STATUS
            next_generation_index += 1
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
                try:
                    generated = pending_generation.result()
                except Exception as exc:
                    dashboard_rows[current_generation.row_index].llm = "error"
                    dashboard_rows[
                        current_generation.row_index
                    ].evaluation = "cancelled"
                    _cancel_pending_work(
                        runner,
                        pending_generation,
                        pending,
                        dashboard_rows,
                    )
                    dashboard.render()
                    raise RuntimeError(
                        f"LLM generation failed for task "
                        f"{current_generation.task.id}: {exc}"
                    ) from exc
                _queue_evaluation(
                    config,
                    runner,
                    evaluation_executor,
                    pending,
                    dashboard_rows,
                    current_generation,
                    generated,
                )
                pending_generation = None
                current_generation = None

                if next_generation_index < len(queued_generations):
                    pending_generation, current_generation = _queue_generation(
                        generation_executor,
                        solution_generators[
                            queued_generations[
                                next_generation_index
                            ].temperature_index
                        ],
                        queued_generations[next_generation_index],
                    )
                    dashboard_rows[
                        queued_generations[next_generation_index].row_index
                    ].llm = LLM_RUNNING_STATUS
                    next_generation_index += 1
                dashboard.render()

            _complete_evaluations(
                config,
                runner,
                pending,
                completed_futures,
                pending_generation,
                dashboard,
                dashboard_rows,
                task_scores_by_temperature,
            )


def _run_prepared_opencode_queue(
    config,
    runner: DockerRunner,
    solution_generators: list[SolutionGenerator],
    queued_generations: list[PendingGeneration],
    dashboard: DashboardRenderer,
    dashboard_rows: list[DashboardRow],
    task_scores_by_temperature: list[list[TaskScore | None]],
) -> None:
    if not queued_generations:
        dashboard.render()
        return

    for generator in solution_generators:
        if not isinstance(generator, OpenCodeGenerator):
            continue
        generator.preflight()

    next_prepare_index = 0
    pending_prepare: Future[PreparedOpenCodeGeneration] | None = None
    current_prepare: PendingGeneration | None = None
    ready_generation: ReadyGeneration | None = None
    pending_generation: Future[GeneratedSolution] | None = None
    current_generation: ReadyGeneration | None = None
    pending: dict[Future[TaskRunResult], PendingEvaluation] = {}

    def queue_prepare(
        prepare_executor: ThreadPoolExecutor,
    ) -> None:
        nonlocal next_prepare_index
        nonlocal pending_prepare
        nonlocal current_prepare
        if pending_prepare is not None or ready_generation is not None:
            return
        if next_prepare_index >= len(queued_generations):
            return
        pending = queued_generations[next_prepare_index]
        generator = solution_generators[pending.temperature_index]
        if not isinstance(generator, OpenCodeGenerator):
            raise RuntimeError("OpenCode prepare ahead requires OpenCode generators.")
        pending_prepare, current_prepare = _queue_opencode_prepare(
            prepare_executor,
            generator,
            pending,
        )
        dashboard_rows[pending.row_index].llm = "preparing"
        next_prepare_index += 1

    def start_ready_generation(
        generation_executor: ThreadPoolExecutor,
        prepare_executor: ThreadPoolExecutor,
    ) -> None:
        nonlocal ready_generation
        nonlocal pending_generation
        nonlocal current_generation
        if pending_generation is not None or ready_generation is None:
            return
        pending_generation = generation_executor.submit(
            _run_prepared_opencode_solution,
            ready_generation.generator,
            ready_generation.prepared,
        )
        current_generation = ready_generation
        dashboard_rows[ready_generation.pending.row_index].llm = LLM_RUNNING_STATUS
        ready_generation = None
        queue_prepare(prepare_executor)

    with ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="benchmark-opencode-prepare",
    ) as prepare_executor, ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="benchmark-llm",
    ) as generation_executor, ThreadPoolExecutor(
        max_workers=config.benchmark.evaluation_workers,
        thread_name_prefix="benchmark-eval",
    ) as evaluation_executor:
        queue_prepare(prepare_executor)
        dashboard.render()

        while (
            pending_prepare is not None
            or ready_generation is not None
            or pending_generation is not None
            or pending
        ):
            start_ready_generation(generation_executor, prepare_executor)
            active_futures: set[Future] = set(pending)
            if pending_prepare is not None:
                active_futures.add(pending_prepare)
            if pending_generation is not None:
                active_futures.add(pending_generation)
            if not active_futures:
                continue

            completed_futures, _ = wait(
                active_futures,
                return_when=FIRST_COMPLETED,
            )

            if (
                pending_prepare is not None
                and pending_prepare in completed_futures
                and current_prepare is not None
            ):
                try:
                    prepared = pending_prepare.result()
                except Exception as exc:
                    dashboard_rows[current_prepare.row_index].llm = "error"
                    dashboard_rows[current_prepare.row_index].evaluation = "cancelled"
                    _cancel_prepared_opencode_work(
                        runner,
                        solution_generators,
                        pending_generation,
                        pending_prepare,
                        current_prepare,
                        pending,
                        ready_generation,
                        dashboard_rows,
                    )
                    dashboard.render()
                    raise RuntimeError(
                        f"OpenCode preparation failed for task "
                        f"{current_prepare.task.id}: {exc}"
                    ) from exc
                generator = solution_generators[current_prepare.temperature_index]
                if not isinstance(generator, OpenCodeGenerator):
                    raise RuntimeError(
                        "OpenCode prepare ahead requires OpenCode generators."
                    )
                ready_generation = ReadyGeneration(
                    pending=current_prepare,
                    generator=generator,
                    prepared=prepared,
                )
                dashboard_rows[current_prepare.row_index].llm = "ready"
                pending_prepare = None
                current_prepare = None
                start_ready_generation(generation_executor, prepare_executor)
                dashboard.render()

            if (
                pending_generation is not None
                and pending_generation in completed_futures
                and current_generation is not None
            ):
                try:
                    generated = pending_generation.result()
                except Exception as exc:
                    dashboard_rows[current_generation.pending.row_index].llm = "error"
                    dashboard_rows[
                        current_generation.pending.row_index
                    ].evaluation = "cancelled"
                    _cancel_prepared_opencode_work(
                        runner,
                        solution_generators,
                        pending_generation,
                        pending_prepare,
                        current_prepare,
                        pending,
                        ready_generation,
                        dashboard_rows,
                    )
                    dashboard.render()
                    raise RuntimeError(
                        f"LLM generation failed for task "
                        f"{current_generation.pending.task.id}: {exc}"
                    ) from exc
                _queue_evaluation(
                    config,
                    runner,
                    evaluation_executor,
                    pending,
                    dashboard_rows,
                    current_generation.pending,
                    generated,
                )
                pending_generation = None
                current_generation = None
                start_ready_generation(generation_executor, prepare_executor)
                dashboard.render()

            _complete_evaluations(
                config,
                runner,
                pending,
                completed_futures,
                pending_generation,
                dashboard,
                dashboard_rows,
                task_scores_by_temperature,
                error_cleanup=lambda: _cancel_prepared_opencode_work(
                    runner,
                    solution_generators,
                    pending_generation,
                    pending_prepare,
                    current_prepare,
                    pending,
                    ready_generation,
                    dashboard_rows,
                ),
            )


def _cancel_pending_work(
    runner: DockerRunner,
    pending_generation: Future[GeneratedSolution] | None,
    pending_evaluations: dict[Future[TaskRunResult], PendingEvaluation],
    rows: list[DashboardRow],
) -> None:
    if pending_generation is not None:
        pending_generation.cancel()
    for future, pending_evaluation in pending_evaluations.items():
        if not future.done():
            rows[pending_evaluation.row_index].evaluation = "cancelled"
        future.cancel()
    runner.cancel()


def _cancel_prepared_opencode_work(
    runner: DockerRunner,
    solution_generators: list[SolutionGenerator],
    pending_generation: Future[GeneratedSolution] | None,
    pending_prepare: Future[PreparedOpenCodeGeneration] | None,
    current_prepare: PendingGeneration | None,
    pending_evaluations: dict[Future[TaskRunResult], PendingEvaluation],
    ready_generation: ReadyGeneration | None,
    rows: list[DashboardRow],
) -> None:
    if ready_generation is not None:
        ready_generation.generator.cleanup_prepared(ready_generation.prepared)
    if pending_prepare is not None:
        pending_prepare.cancel()
        if pending_prepare.done() and not pending_prepare.cancelled():
            try:
                prepared = pending_prepare.result()
            except Exception:
                prepared = None
            if prepared is not None:
                generator: SolutionGenerator | None = None
                if current_prepare is not None:
                    generator = solution_generators[current_prepare.temperature_index]
                if isinstance(generator, OpenCodeGenerator):
                    generator.cleanup_prepared(prepared)
    _cancel_pending_work(runner, pending_generation, pending_evaluations, rows)


def _queue_generation(
    executor: ThreadPoolExecutor,
    generator: SolutionGenerator,
    pending_generation: PendingGeneration,
) -> tuple[Future[GeneratedSolution], PendingGeneration]:
    task_dir = pending_generation.task_dir
    task_dir.mkdir(parents=True, exist_ok=True)
    return (
        executor.submit(
            _generate_solution,
            generator,
            pending_generation.task,
            task_dir,
        ),
        pending_generation,
    )


def _queue_opencode_prepare(
    executor: ThreadPoolExecutor,
    generator: OpenCodeGenerator,
    pending_generation: PendingGeneration,
) -> tuple[Future[PreparedOpenCodeGeneration], PendingGeneration]:
    task_dir = pending_generation.task_dir
    task_dir.mkdir(parents=True, exist_ok=True)
    return (
        executor.submit(
            _prepare_opencode_solution,
            generator,
            pending_generation.task,
            task_dir,
        ),
        pending_generation,
    )


def _generate_solution(
    generator: SolutionGenerator,
    task: Task,
    task_dir: Path,
) -> GeneratedSolution:
    return generator.generate(task, task_dir)


def _prepare_opencode_solution(
    generator: OpenCodeGenerator,
    task: Task,
    task_dir: Path,
) -> PreparedOpenCodeGeneration:
    return generator.prepare(task, task_dir)


def _run_prepared_opencode_solution(
    generator: OpenCodeGenerator,
    prepared: PreparedOpenCodeGeneration,
) -> GeneratedSolution:
    return generator.run_prepared(prepared)


def _queue_evaluation(
    config,
    runner: DockerRunner,
    evaluation_executor: ThreadPoolExecutor,
    pending_evaluations: dict[Future[TaskRunResult], PendingEvaluation],
    dashboard_rows: list[DashboardRow],
    current_generation: PendingGeneration,
    generated: GeneratedSolution,
) -> None:
    row = dashboard_rows[current_generation.row_index]
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
        generator=generated.generator,
        opencode_metadata=opencode_metadata_to_dict(
            generated.opencode_metadata
        ),
        temperature=current_generation.temperature,
    )
    pending_evaluations[evaluation_future] = PendingEvaluation(
        row_index=current_generation.row_index,
        task_index=current_generation.task_index,
        temperature_index=current_generation.temperature_index,
        temperature=current_generation.temperature,
        task=current_generation.task,
        task_dir=current_generation.task_dir,
    )
    _refresh_evaluation_statuses(
        pending_evaluations,
        dashboard_rows,
        config.benchmark.evaluation_workers,
    )


def _complete_evaluations(
    config,
    runner: DockerRunner,
    pending_evaluations: dict[Future[TaskRunResult], PendingEvaluation],
    completed_futures: set[Future],
    pending_generation: Future[GeneratedSolution] | None,
    dashboard: DashboardRenderer,
    dashboard_rows: list[DashboardRow],
    task_scores_by_temperature: list[list[TaskScore | None]],
    error_cleanup=None,
) -> None:
    for completed_future in completed_futures:
        if completed_future not in pending_evaluations:
            continue
        pending_evaluation = pending_evaluations.pop(completed_future)
        try:
            result = completed_future.result()
        except Exception as exc:
            dashboard_rows[pending_evaluation.row_index].evaluation = "error"
            if error_cleanup is None:
                _cancel_pending_work(
                    runner,
                    pending_generation,
                    pending_evaluations,
                    dashboard_rows,
                )
            else:
                error_cleanup()
            dashboard.render()
            raise RuntimeError(
                f"Evaluation failed for task "
                f"{pending_evaluation.task.id}: {exc}"
            ) from exc
        write_result_json(
            pending_evaluation.task_dir / "result.json",
            result,
            model=config.llm.model,
            model_label=config.llm.effective_model_label,
            company=config.llm.company,
        )
        task_score = score_task(pending_evaluation.task, result)
        task_scores_by_temperature[pending_evaluation.temperature_index][
            pending_evaluation.task_index
        ] = task_score
        dashboard_rows[pending_evaluation.row_index].evaluation = (
            _format_evaluation_status(
                pending_evaluation.task,
                result,
                task_score,
            )
        )
        _refresh_evaluation_statuses(
            pending_evaluations,
            dashboard_rows,
            config.benchmark.evaluation_workers,
        )
        dashboard.render()


def _completed_task_scores(task_scores: list[TaskScore | None]) -> list[TaskScore]:
    completed = [task_score for task_score in task_scores if task_score is not None]
    if len(completed) != len(task_scores):
        raise RuntimeError("Some task evaluations did not complete.")
    return completed


def _temperature_task_root(
    run_dir: Path,
    temperature: float,
    *,
    multi_temperature: bool,
) -> Path:
    if not multi_temperature:
        return run_dir
    return run_dir / "temperatures" / f"temperature-{_format_temperature(temperature)}"


def _select_best_temperature_run(
    temperature_runs: list[TemperatureRun],
) -> TemperatureRun:
    if not temperature_runs:
        raise RuntimeError("No temperature runs completed.")
    return max(
        enumerate(temperature_runs),
        key=lambda item: (
            item[1].score.earned_points,
            item[1].score.final_score,
            -item[0],
        ),
    )[1]


def _load_existing_task_score(
    task: Task,
    result_path: Path,
    task_scores: list[TaskScore | None],
    dashboard_rows: list[DashboardRow],
    *,
    task_index: int,
    row_index: int,
    expected_temperature: float,
    prefix: str,
) -> None:
    result = _read_task_result_json(result_path)
    if result.task_id != task.id:
        raise ValueError(
            f"{result_path} belongs to {result.task_id}, expected {task.id}"
        )
    if result.temperature is not None and not _same_temperature(
        result.temperature,
        expected_temperature,
    ):
        raise ValueError(
            f"{result_path} has temperature "
            f"{_format_temperature(result.temperature)}, expected "
            f"{_format_temperature(expected_temperature)}"
        )
    if result.temperature is None:
        result = replace(result, temperature=expected_temperature)

    task_score = score_task(task, result)
    task_scores[task_index] = task_score
    dashboard_rows[row_index].llm = f"{task_score.llm_response_time_seconds:.2f}s"
    dashboard_rows[row_index].tokens = _format_tokens(
        task_score.llm_usage.total_tokens
    )
    dashboard_rows[row_index].evaluation = (
        prefix
        + _format_evaluation_status(
            task,
            result,
            task_score,
        )
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
        generator=str(data.get("generator") or "llm"),
        opencode_metadata=(
            data.get("opencode") if isinstance(data.get("opencode"), dict) else None
        ),
        temperature=_optional_float(data.get("temperature")),
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
            key=lambda pending: pending.row_index,
        )
    ):
        rows[pending.row_index].evaluation = (
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


def _optional_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
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


def _format_temperature(temperature: float) -> str:
    return f"{temperature:g}"


def _same_temperature(left: float, right: float) -> bool:
    return abs(left - right) < 1e-9


if __name__ == "__main__":
    raise SystemExit(main())
