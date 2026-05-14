from __future__ import annotations

import argparse
import sys
from pathlib import Path

from benchmark.config import apply_cli_overrides, load_config
from benchmark.llm_client import LlmClient, extract_solution_code
from benchmark.report import create_run_dir, write_summary
from benchmark.runner import DockerRunner, write_result_json
from benchmark.scorer import score_benchmark, score_task
from benchmark.tasks import load_tasks, validate_tasks


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
    )
    tasks = load_tasks(config.benchmark.difficulty)
    tasks = _filter_tasks(tasks, config.benchmark.task_id)
    errors = validate_tasks(tasks)
    if errors:
        raise RuntimeError("Task validation failed:\n" + "\n".join(errors))

    run_dir = create_run_dir(config.benchmark.output_dir)
    client = LlmClient(config.llm)
    runner = DockerRunner(config.docker)
    task_scores = []

    print(f"Run directory: {run_dir}")
    for task in tasks:
        print(f"Running {task.id}: {task.name}")
        task_dir = run_dir / "tasks" / task.id
        task_dir.mkdir(parents=True, exist_ok=True)
        prompt = task.prompt
        (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        llm_response = client.complete(prompt)
        (task_dir / "response.md").write_text(
            llm_response.content, encoding="utf-8"
        )
        required_public_class = (
            task.solution_class if task.difficulty == "easy" else None
        )
        extracted = extract_solution_code(
            llm_response.content,
            required_public_class=required_public_class,
        )
        if extracted.code is not None:
            generated_path = task_dir / task.generated_file
            generated_path.parent.mkdir(parents=True, exist_ok=True)
            generated_path.write_text(extracted.code, encoding="utf-8")

        result = runner.evaluate(
            task,
            extracted,
            artifact_dir=task_dir,
            llm_response_time_seconds=llm_response.response_time_seconds,
            llm_usage=llm_response.usage,
        )
        write_result_json(task_dir / "result.json", result)
        task_score = score_task(task, result)
        task_scores.append(task_score)

        print(f"  {result.status}: {task_score.earned_points:g}/{task_score.available_points:g}")
        print(f"  LLM: {task_score.llm_response_time_seconds:.2f}s")
        print(f"  Tokens: {_format_tokens(task_score.llm_usage.total_tokens)}")

    benchmark_score = score_benchmark(task_scores)
    write_summary(
        run_dir,
        config=config,
        score=benchmark_score,
        task_scores=task_scores,
    )
    print(
        f"Final score: {benchmark_score.final_score} "
        f"({benchmark_score.earned_points:g}/{benchmark_score.available_points:g})"
    )
    total_llm_time = sum(
        task_score.llm_response_time_seconds for task_score in task_scores
    )
    print(f"Total LLM response time: {total_llm_time:.2f}s")
    total_llm_tokens = _sum_known_tokens(
        task_score.llm_usage.total_tokens for task_score in task_scores
    )
    print(f"Total LLM tokens: {_format_tokens(total_llm_tokens)}")
    return 0


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
