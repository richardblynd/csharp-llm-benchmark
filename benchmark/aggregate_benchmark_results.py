from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DIFFICULTIES = ("easy", "medium", "hard")


@dataclass(frozen=True)
class BenchmarkResult:
    run_name: str
    model: str
    company: str
    quantization: str
    total_seconds: float | None
    total_tokens: int | None
    tokens_per_second: float | None
    difficulty_scores: dict[str, float | None]
    final_score: float | None
    earned_points: float | None
    available_points: float | None


def main() -> int:
    args = parse_args()
    results_dir = args.results_dir.resolve()
    output_path = (
        args.output.resolve()
        if args.output is not None
        else results_dir / "benchmark_results.md"
    )

    benchmark_results = collect_benchmark_results(results_dir)
    markdown = render_markdown(benchmark_results, results_dir)
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Wrote {len(benchmark_results)} benchmark results to {output_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate benchmark run summaries from a results directory into one "
            "Markdown ranking table."
        )
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing benchmark run folders. Defaults to ./results.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Markdown file to write. Defaults to benchmark_results.md inside "
            "the results directory."
        ),
    )
    return parser.parse_args()


def collect_benchmark_results(results_dir: Path) -> list[BenchmarkResult]:
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")
    if not results_dir.is_dir():
        raise NotADirectoryError(f"Results path is not a directory: {results_dir}")

    benchmark_results: list[BenchmarkResult] = []
    for run_dir in sorted(path for path in results_dir.iterdir() if path.is_dir()):
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue

        payload = load_json(summary_path)
        tasks = [task for task in payload.get("tasks", []) if isinstance(task, dict)]
        benchmark_results.append(parse_summary(run_dir.name, payload, tasks))

    benchmark_results.sort(
        key=lambda result: (
            result.final_score is not None,
            result.final_score if result.final_score is not None else -1.0,
            result.tokens_per_second
            if result.tokens_per_second is not None
            else -1.0,
        ),
        reverse=True,
    )
    return benchmark_results


def parse_summary(
    run_name: str,
    payload: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> BenchmarkResult:
    llm_payload = payload.get("llm", {})
    if not isinstance(llm_payload, dict):
        llm_payload = {}

    model = str(
        payload.get("modelLabel")
        or llm_payload.get("modelLabel")
        or payload.get("model_label")
        or llm_payload.get("model_label")
        or payload.get("model")
        or llm_payload.get("model")
        or run_name
    )
    company = str(payload.get("company") or llm_payload.get("company") or "")
    quantization = str(
        payload.get("quantization")
        or llm_payload.get("quantization")
        or infer_quantization(run_name)
        or ""
    )

    total_seconds = sum_optional_numbers(
        task.get("llm_response_time_seconds") for task in tasks
    )
    if total_seconds is None:
        total_seconds = optional_float(
            payload.get("llm_response_time", {}).get("total_seconds")
        )

    total_tokens = sum_optional_ints(
        nested_get(task, "llm_usage", "total_tokens") for task in tasks
    )
    if total_tokens is None:
        total_tokens = optional_int(
            payload.get("llm_token_usage", {}).get("total_tokens")
        )

    earned_points = sum_optional_numbers(task.get("earned_points") for task in tasks)
    available_points = sum_optional_numbers(
        task.get("available_points") for task in tasks
    )
    if earned_points is None:
        earned_points = optional_float(payload.get("score", {}).get("earned_points"))
    if available_points is None:
        available_points = optional_float(
            payload.get("score", {}).get("available_points")
        )

    difficulty_scores = {
        difficulty: calculate_score(
            task
            for task in tasks
            if str(task.get("task_id", "")).startswith(f"{difficulty}-")
        )
        for difficulty in DIFFICULTIES
    }

    final_score = calculate_score(tasks)
    if final_score is None:
        final_score = optional_float(payload.get("score", {}).get("final_score"))

    tokens_per_second = None
    if total_tokens is not None and total_seconds is not None and total_seconds > 0:
        tokens_per_second = total_tokens / total_seconds

    return BenchmarkResult(
        run_name=run_name,
        model=model,
        company=company,
        quantization=quantization,
        total_seconds=total_seconds,
        total_tokens=total_tokens,
        tokens_per_second=tokens_per_second,
        difficulty_scores=difficulty_scores,
        final_score=final_score,
        earned_points=earned_points,
        available_points=available_points,
    )


def calculate_score(tasks: Iterable[dict[str, Any]]) -> float | None:
    earned = 0.0
    available = 0.0
    found_points = False

    for task in tasks:
        task_earned = optional_float(task.get("earned_points"))
        task_available = optional_float(task.get("available_points"))
        if task_earned is None or task_available is None:
            continue
        found_points = True
        earned += task_earned
        available += task_available

    if not found_points:
        return None
    if available <= 0:
        return 0.0
    return round((earned / available) * 100, 2)


def render_markdown(
    benchmark_results: list[BenchmarkResult],
    results_dir: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# LLM Benchmark Results",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Results directory: `{results_dir}`",
        f"- Benchmark runs: `{len(benchmark_results)}`",
        "",
        "| Rank | Model | Company | Quantization | Total time | Total tokens | Tokens/s | Easy score | Medium score | Hard score | Final score |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for rank, result in enumerate(benchmark_results, start=1):
        lines.append(
            "| {rank} | {model} | {company} | {quantization} | {total_time} | {total_tokens} | {tokens_per_second} | {easy_score} | {medium_score} | {hard_score} | {final_score} |".format(
                rank=rank,
                model=markdown_code(result.model),
                company=markdown_code(result.company or "n/a"),
                quantization=markdown_code(result.quantization or "n/a"),
                total_time=markdown_code(format_duration(result.total_seconds)),
                total_tokens=format_int(result.total_tokens),
                tokens_per_second=format_number(result.tokens_per_second),
                easy_score=format_score(result.difficulty_scores["easy"]),
                medium_score=format_score(result.difficulty_scores["medium"]),
                hard_score=format_score(result.difficulty_scores["hard"]),
                final_score=format_score(result.final_score),
            )
        )

    lines.append("")
    return "\n".join(lines)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def infer_quantization(run_name: str) -> str | None:
    match = re.search(r"\b(Q\d(?:_[A-Z0-9]+)+)\b", run_name, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(1).upper()


def sum_optional_numbers(values: Iterable[Any]) -> float | None:
    total = 0.0
    found = False
    for value in values:
        number = optional_float(value)
        if number is None:
            continue
        found = True
        total += number
    return total if found else None


def sum_optional_ints(values: Iterable[Any]) -> int | None:
    total = 0
    found = False
    for value in values:
        number = optional_int(value)
        if number is None:
            continue
        found = True
        total += number
    return total if found else None


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"

    rounded_seconds = int(seconds + 0.5)
    hours, remainder = divmod(rounded_seconds, 60 * 60)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_int(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}"


def format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def format_score(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def markdown_code(value: str) -> str:
    return "`" + value.replace("`", "\\`").replace("|", "\\|") + "`"


if __name__ == "__main__":
    raise SystemExit(main())
