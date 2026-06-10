from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DIFFICULTIES = ("easy", "medium", "hard")
TAG_COLORS = (
    {"bg": "#1d4ed8", "border": "#93c5fd", "text": "#ffffff"},
    {"bg": "#facc15", "border": "#a16207", "text": "#1f2937"},
    {"bg": "#7e22ce", "border": "#c084fc", "text": "#ffffff"},
    {"bg": "#047857", "border": "#6ee7b7", "text": "#ffffff"},
    {"bg": "#be123c", "border": "#fda4af", "text": "#ffffff"},
    {"bg": "#334155", "border": "#cbd5e1", "text": "#ffffff"},
    {"bg": "#0891b2", "border": "#67e8f9", "text": "#ffffff"},
    {"bg": "#ea580c", "border": "#fed7aa", "text": "#ffffff"},
)


@dataclass(frozen=True)
class BenchmarkResult:
    run_name: str
    generator: str
    model: str
    company: str
    quantization: str
    total_seconds: float | None
    total_tokens: int | None
    highest_token_task_id: str | None
    highest_token_task_total_tokens: int | None
    tokens_per_second: float | None
    difficulty_scores: dict[str, float | None]
    selected_temperature: float | None
    temperature_scores: dict[str, float | None]
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
    html_output_path = (
        args.html_output.resolve()
        if args.html_output is not None
        else output_path.with_suffix(".html")
    )

    benchmark_results = collect_benchmark_results(results_dir)
    markdown = render_markdown(benchmark_results, results_dir)
    output_path.write_text(markdown, encoding="utf-8")
    html_page = render_html(benchmark_results, results_dir)
    html_output_path.write_text(html_page, encoding="utf-8")

    print(
        f"Wrote {len(benchmark_results)} benchmark results to "
        f"{output_path} and {html_output_path}"
    )
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
    parser.add_argument(
        "--html-output",
        type=Path,
        default=None,
        help=(
            "HTML file to write. Defaults to the Markdown output path with "
            "the .html extension."
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
    generator = normalize_generator(payload.get("generator"))
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
    highest_token_task_id, highest_token_task_total_tokens = find_highest_token_task(
        payload,
        tasks,
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
    selected_temperature = optional_float(
        payload.get("selected_temperature", llm_payload.get("temperature"))
    )
    temperature_scores = parse_temperature_scores(payload)

    tokens_per_second = None
    if total_tokens is not None and total_seconds is not None and total_seconds > 0:
        tokens_per_second = total_tokens / total_seconds

    return BenchmarkResult(
        run_name=run_name,
        generator=generator,
        model=model,
        company=company,
        quantization=quantization,
        total_seconds=total_seconds,
        total_tokens=total_tokens,
        highest_token_task_id=highest_token_task_id,
        highest_token_task_total_tokens=highest_token_task_total_tokens,
        tokens_per_second=tokens_per_second,
        difficulty_scores=difficulty_scores,
        selected_temperature=selected_temperature,
        temperature_scores=temperature_scores,
        final_score=final_score,
        earned_points=earned_points,
        available_points=available_points,
    )


def parse_temperature_scores(payload: dict[str, Any]) -> dict[str, float | None]:
    scores: dict[str, float | None] = {}
    raw_scores = payload.get("temperature_scores")
    if not isinstance(raw_scores, list):
        return scores

    for entry in raw_scores:
        if not isinstance(entry, dict):
            continue
        temperature = optional_float(entry.get("temperature"))
        if temperature is None:
            continue
        score = entry.get("score")
        final_score = (
            optional_float(score.get("final_score"))
            if isinstance(score, dict)
            else None
        )
        scores[format_temperature_label(temperature)] = final_score
    return scores


def find_highest_token_task(
    payload: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> tuple[str | None, int | None]:
    summary_task = payload.get("highest_token_task")
    if isinstance(summary_task, dict):
        task_id = summary_task.get("task_id")
        total_tokens = optional_int(summary_task.get("total_tokens"))
        if task_id is not None and total_tokens is not None:
            return str(task_id), total_tokens

    highest_task_id: str | None = None
    highest_total_tokens: int | None = None
    for task in tasks:
        task_id = task.get("task_id")
        total_tokens = optional_int(nested_get(task, "llm_usage", "total_tokens"))
        if task_id is None or total_tokens is None:
            continue
        if highest_total_tokens is None or total_tokens > highest_total_tokens:
            highest_task_id = str(task_id)
            highest_total_tokens = total_tokens

    return highest_task_id, highest_total_tokens


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


def collect_temperature_labels(
    benchmark_results: list[BenchmarkResult],
) -> list[str]:
    labels = {
        label
        for result in benchmark_results
        for label in result.temperature_scores
    }
    return sorted(labels, key=temperature_label_sort_key)


def temperature_label_sort_key(label: str) -> tuple[int, float | str]:
    number = optional_float(label)
    if number is not None:
        return (0, number)
    return (1, label)


def temperature_score_key(index: int) -> str:
    return f"temperaturescore{index}"


def format_temperature_label(temperature: float) -> str:
    return f"{temperature:g}"


def render_markdown(
    benchmark_results: list[BenchmarkResult],
    results_dir: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    temperature_labels = collect_temperature_labels(benchmark_results)
    temperature_headers = " | ".join(
        f"Temp {label}" for label in temperature_labels
    )
    temperature_alignments = " | ".join("---:" for _label in temperature_labels)
    temperature_header_segment = (
        f" | Best temp | {temperature_headers}" if temperature_headers else " | Best temp"
    )
    temperature_alignment_segment = (
        f" | ---: | {temperature_alignments}" if temperature_alignments else " | ---:"
    )
    lines = [
        "# LLM Benchmark Results",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Results directory: `{results_dir}`",
        f"- Benchmark runs: `{len(benchmark_results)}`",
        "",
        f"| Rank | Generator | Model | Company | Quantization | Total time | Total tokens | Max task tokens | Max token task | Tokens/s | Easy score | Medium score | Hard score | Final score{temperature_header_segment} |",
        f"| ---: | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---:{temperature_alignment_segment} |",
    ]

    for rank, result in enumerate(benchmark_results, start=1):
        temperature_values = " | ".join(
            format_score(result.temperature_scores.get(label))
            for label in temperature_labels
        )
        temperature_value_segment = (
            f" | {format_temperature(result.selected_temperature)} | {temperature_values}"
            if temperature_values
            else f" | {format_temperature(result.selected_temperature)}"
        )
        lines.append(
            "| {rank} | {generator} | {model} | {company} | {quantization} | {total_time} | {total_tokens} | {highest_token_total} | {highest_token_task} | {tokens_per_second} | {easy_score} | {medium_score} | {hard_score} | {final_score}{temperature_values} |".format(
                rank=rank,
                generator=markdown_code(result.generator),
                model=markdown_code(result.model),
                company=markdown_code(result.company or "n/a"),
                quantization=markdown_code(result.quantization or "n/a"),
                total_time=markdown_code(format_duration(result.total_seconds)),
                total_tokens=format_int(result.total_tokens),
                highest_token_total=format_int(result.highest_token_task_total_tokens),
                highest_token_task=markdown_code(result.highest_token_task_id or "n/a"),
                tokens_per_second=format_number(result.tokens_per_second),
                easy_score=format_score(result.difficulty_scores["easy"]),
                medium_score=format_score(result.difficulty_scores["medium"]),
                hard_score=format_score(result.difficulty_scores["hard"]),
                final_score=format_score(result.final_score),
                temperature_values=temperature_value_segment,
            )
        )

    lines.append("")
    return "\n".join(lines)


def render_html(
    benchmark_results: list[BenchmarkResult],
    results_dir: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    temperature_columns = [
        (label, temperature_score_key(index))
        for index, label in enumerate(collect_temperature_labels(benchmark_results))
    ]
    temperature_header_cells = render_temperature_header_cells(temperature_columns)
    generators = sorted(
        {result.generator for result in benchmark_results if result.generator}
    )
    companies = sorted(
        {result.company for result in benchmark_results if result.company}
    )
    quantizations = sorted(
        {result.quantization for result in benchmark_results if result.quantization}
    )
    quantization_colors = build_tag_colors(
        sorted({result.quantization or "n/a" for result in benchmark_results})
    )
    rows = "\n".join(
        render_html_row(rank, result, quantization_colors, temperature_columns)
        for rank, result in enumerate(benchmark_results, start=1)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LLM Benchmark Results</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #202124;
      --muted: #626760;
      --line: #d8dad4;
      --accent: #176b87;
      --accent-strong: #104f64;
      --thead: #eef2f1;
      --shadow: 0 8px 24px rgb(31 41 55 / 10%);
      --best-bg: #dbeafe;
      --best-border: #60a5fa;
      --best-text: #1e3a8a;
      --worst-bg: #fee2e2;
      --worst-border: #f87171;
      --worst-text: #991b1b;
    }}

    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #151719;
        --panel: #1f2326;
        --text: #f1f3f2;
        --muted: #aeb7b1;
        --line: #343a3f;
        --accent: #66c2d7;
        --accent-strong: #8fd8e8;
        --thead: #293036;
        --shadow: 0 8px 24px rgb(0 0 0 / 24%);
        --best-bg: #1e3a5f;
        --best-border: #60a5fa;
        --best-text: #dbeafe;
        --worst-bg: #5f2323;
        --worst-border: #f87171;
        --worst-text: #fee2e2;
      }}
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.45;
    }}

    main {{
      width: min(1500px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0;
    }}

    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      font-weight: 700;
      letter-spacing: 0;
    }}

    .meta {{
      margin: 0 0 24px;
      color: var(--muted);
      font-size: 14px;
    }}

    .filters {{
      display: grid;
      grid-template-columns: minmax(240px, 1fr) repeat(4, minmax(150px, 220px));
      gap: 12px;
      align-items: end;
      margin-bottom: 16px;
    }}

    label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}

    input,
    select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
      padding: 8px 10px;
      font: inherit;
    }}

    input[type="range"] {{
      min-height: 0;
      padding: 0;
      accent-color: var(--accent);
    }}

    input:focus,
    select:focus,
    button:focus {{
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }}

    .score-range {{
      gap: 8px;
    }}

    .range-fields {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}

    .range-fields input {{
      min-height: 34px;
      font-variant-numeric: tabular-nums;
    }}

    .range-slider {{
      position: relative;
      --range-thumb-size: 18px;
      --range-track-height: 4px;
      height: 26px;
    }}

    .range-base,
    .range-fill {{
      position: absolute;
      top: 50%;
      right: 0;
      left: 0;
      height: var(--range-track-height);
      border-radius: 999px;
      transform: translateY(-50%);
    }}

    .range-base {{
      background: color-mix(in srgb, var(--line) 82%, var(--text) 18%);
    }}

    .range-fill {{
      background: var(--accent);
    }}

    .range-slider input {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 26px;
      background: transparent;
      appearance: none;
      margin: 0;
      pointer-events: none;
    }}

    .range-slider input::-webkit-slider-runnable-track {{
      height: var(--range-track-height);
      background: transparent;
    }}

    .range-slider input::-moz-range-track {{
      height: var(--range-track-height);
      background: transparent;
    }}

    .range-slider input::-webkit-slider-thumb {{
      width: var(--range-thumb-size);
      height: var(--range-thumb-size);
      border: 2px solid var(--panel);
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 1px var(--accent-strong);
      appearance: none;
      box-sizing: border-box;
      margin-top: calc((var(--range-track-height) - var(--range-thumb-size)) / 2);
      pointer-events: auto;
    }}

    .range-slider input::-moz-range-thumb {{
      width: var(--range-thumb-size);
      height: var(--range-thumb-size);
      border: 2px solid var(--panel);
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 1px var(--accent-strong);
      box-sizing: border-box;
      pointer-events: auto;
    }}

    .column-options {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: -4px 0 16px;
    }}

    .check-option {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
      cursor: pointer;
      font-size: 13px;
      font-weight: 700;
      padding: 7px 10px;
      text-transform: none;
    }}

    .check-option input {{
      width: 16px;
      min-height: 16px;
      margin: 0;
      accent-color: var(--accent);
    }}

    .summary {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 14px;
    }}

    button {{
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--accent);
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      padding: 7px 12px;
    }}

    button:hover {{
      color: var(--accent-strong);
      border-color: var(--accent);
    }}

    .table-wrap {{
      overflow: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1180px;
    }}

    th,
    td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      white-space: nowrap;
      font-size: 14px;
    }}

    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--thead);
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      user-select: none;
      cursor: pointer;
    }}

    th[data-key]:not(.group-heading)::after,
    th.group-heading[data-key][rowspan="2"]::after {{
      content: " <>";
      color: var(--muted);
      font-weight: 400;
    }}

    th[data-key]:not(.group-heading)[data-sort-active="asc"]::after,
    th.group-heading[data-key][rowspan="2"][data-sort-active="asc"]::after {{
      content: " ^";
      color: var(--accent);
    }}

    th[data-key]:not(.group-heading)[data-sort-active="desc"]::after,
    th.group-heading[data-key][rowspan="2"][data-sort-active="desc"]::after {{
      content: " v";
      color: var(--accent);
    }}

    thead tr:first-child th {{
      top: 0;
    }}

    thead tr:nth-child(2) th {{
      top: 33px;
    }}

    td.numeric,
    th.numeric {{
      text-align: right;
    }}

    th.group-heading {{
      text-align: right;
    }}

    th.group-heading[data-expanded="true"] {{
      text-align: center;
    }}

    tbody tr:hover {{
      background: rgb(23 107 135 / 8%);
    }}

    td.extreme-best,
    td.extreme-worst {{
      border-left: 3px solid transparent;
      font-weight: 800;
    }}

    td.extreme-best {{
      background: var(--best-bg);
      border-left-color: var(--best-border);
      color: var(--best-text);
    }}

    td.extreme-worst {{
      background: var(--worst-bg);
      border-left-color: var(--worst-border);
      color: var(--worst-text);
    }}

    .model {{
      font-weight: 700;
    }}

    .model-button {{
      min-height: auto;
      border: 0;
      border-radius: 0;
      background: transparent;
      color: inherit;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      padding: 0;
      text-align: left;
    }}

    .model-button:hover {{
      border-color: transparent;
      color: var(--accent);
      text-decoration: underline;
    }}

    .tag {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      border: 1px solid var(--tag-border);
      border-radius: 999px;
      background: var(--tag-bg);
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tag-border) 68%, transparent);
      color: var(--tag-text);
      font-size: 12px;
      font-weight: 700;
      padding: 2px 9px;
    }}

    .chart-section {{
      margin-top: 20px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 16px;
    }}

    .chart-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}

    .chart-header h2 {{
      margin: 0;
      font-size: 16px;
      letter-spacing: 0;
    }}

    .chart-header span {{
      color: var(--muted);
      font-size: 13px;
    }}

    .score-chart {{
      display: grid;
      gap: 8px;
    }}

    .chart-row {{
      display: grid;
      grid-template-columns: minmax(260px, 460px) minmax(120px, 1fr) 56px;
      gap: 10px;
      align-items: center;
    }}

    .chart-label {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(48px, 84px) minmax(72px, 120px);
      gap: 8px;
      align-items: baseline;
      overflow: hidden;
      font-size: 13px;
    }}

    .chart-label > span {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .chart-label .chart-model {{
      color: var(--text);
      font-weight: 700;
    }}

    .chart-label .chart-quant,
    .chart-label .chart-generator {{
      color: var(--muted);
    }}

    .chart-track {{
      height: 18px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: color-mix(in srgb, var(--panel) 76%, var(--text) 10%);
    }}

    .chart-bar {{
      height: 100%;
      min-width: 2px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), var(--accent-strong));
    }}

    .chart-value {{
      color: var(--text);
      font-size: 13px;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
      text-align: right;
    }}

    .tradeoff-chart {{
      display: grid;
      gap: 12px;
    }}

    .tradeoff-plot {{
      position: relative;
      min-height: 340px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background:
        linear-gradient(var(--line) 1px, transparent 1px),
        linear-gradient(90deg, var(--line) 1px, transparent 1px),
        color-mix(in srgb, var(--panel) 92%, var(--text) 4%);
      background-size: 100% 25%, 25% 100%, 100% 100%;
      padding: 28px 34px 42px 58px;
    }}

    .tradeoff-inner {{
      position: relative;
      height: 270px;
      border-left: 1px solid var(--muted);
      border-bottom: 1px solid var(--muted);
    }}

    .scatter-point {{
      position: absolute;
      width: 14px;
      height: 14px;
      min-height: 14px;
      border: 2px solid var(--panel);
      border-radius: 999px;
      background: var(--point-color);
      box-shadow: 0 0 0 1px color-mix(in srgb, var(--point-color) 78%, #000000 22%), 0 2px 8px rgb(0 0 0 / 22%);
      cursor: pointer;
      padding: 0;
      transform: translate(-50%, 50%);
    }}

    .scatter-point:hover,
    .scatter-point:focus {{
      border-color: var(--text);
      transform: translate(-50%, 50%) scale(1.2);
    }}

    .axis-label {{
      position: absolute;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}

    .axis-label-x {{
      right: 34px;
      bottom: 12px;
    }}

    .axis-label-y {{
      top: 24px;
      left: 14px;
      transform: rotate(-90deg);
      transform-origin: left top;
    }}

    .axis-value {{
      position: absolute;
      color: var(--muted);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }}

    .axis-x-min {{
      left: 58px;
      bottom: 18px;
    }}

    .axis-x-max {{
      right: 34px;
      bottom: 18px;
    }}

    .axis-y-min {{
      left: 18px;
      bottom: 40px;
    }}

    .axis-y-max {{
      left: 18px;
      top: 22px;
    }}

    .tradeoff-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
    }}

    .legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}

    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--point-color);
      box-shadow: 0 0 0 1px color-mix(in srgb, var(--point-color) 78%, #000000 22%);
    }}

    .empty {{
      display: none;
      padding: 24px;
      color: var(--muted);
      text-align: center;
    }}

    @media (max-width: 900px) {{
      main {{
        width: min(100% - 20px, 1500px);
        padding: 20px 0;
      }}

      .filters {{
        grid-template-columns: 1fr;
      }}

      .summary {{
        display: grid;
      }}

      .chart-row {{
        grid-template-columns: 1fr 64px;
      }}

      .chart-label {{
        grid-column: 1 / -1;
      }}

      .tradeoff-plot {{
        min-height: 300px;
        padding: 24px 20px 40px 48px;
      }}

      .tradeoff-inner {{
        height: 230px;
      }}

      .axis-x-min {{
        left: 48px;
      }}

      .axis-x-max,
      .axis-label-x {{
        right: 20px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>LLM Benchmark Results</h1>
    <p class="meta">
      Generated at <code>{escape_html(generated_at)}</code> from
      <code>{escape_html(str(results_dir))}</code>.
    </p>

    <section class="filters" aria-label="Table filters">
      <label>
        Search
        <input id="search" type="search" placeholder="Generator, model, company, quantization, task...">
      </label>
      <label>
        Generator
        <select id="generator">
          <option value="">All generators</option>
          {render_options(generators)}
        </select>
      </label>
      <label>
        Company
        <select id="company">
          <option value="">All companies</option>
          {render_options(companies)}
        </select>
      </label>
      <label>
        Quantization
        <select id="quantization">
          <option value="">All quantizations</option>
          {render_options(quantizations)}
        </select>
      </label>
      <label class="score-range">
        Final score range
        <span class="range-fields">
          <input id="min-score" type="number" min="0" max="100" step="0.01" value="0" aria-label="Minimum final score">
          <input id="max-score" type="number" min="0" max="100" step="0.01" value="100" aria-label="Maximum final score">
        </span>
        <span class="range-slider" aria-hidden="true">
          <span class="range-base"></span>
          <span class="range-fill" id="score-range-fill"></span>
          <input id="min-score-slider" type="range" min="0" max="100" step="0.01" value="0" tabindex="-1">
          <input id="max-score-slider" type="range" min="0" max="100" step="0.01" value="100" tabindex="-1">
        </span>
      </label>
    </section>

    <section class="column-options" aria-label="Column visibility">
      <label class="check-option">
        <input id="show-token-columns" type="checkbox">
        Show max token task columns
      </label>
      <label class="check-option">
        <input id="show-score-columns" type="checkbox">
        Show Easy/Medium/Hard scores
      </label>
      <label class="check-option">
        <input id="show-temperature-columns" type="checkbox">
        Show temperature scores
      </label>
    </section>

    <div class="summary">
      <span id="visible-count">Showing {len(benchmark_results)} of {len(benchmark_results)} runs</span>
      <button id="reset" type="button">Reset filters</button>
    </div>

    <div class="table-wrap">
      <table id="results-table">
        <thead>
          <tr>
            <th class="numeric" rowspan="2" data-key="rank" data-type="number">Rank</th>
            <th rowspan="2" data-key="generator" data-type="text">Generator</th>
            <th rowspan="2" data-key="model" data-type="text">Model</th>
            <th rowspan="2" data-key="company" data-type="text">Company</th>
            <th rowspan="2" data-key="quantization" data-type="text" title="Quantization" aria-label="Quantization">Quant.</th>
            <th class="numeric" rowspan="2" data-key="totalSeconds" data-type="number">Total time</th>
            <th id="token-group-heading" class="group-heading" colspan="1" rowspan="2" data-key="totalTokens" data-type="number">Total tokens</th>
            <th class="numeric" rowspan="2" data-key="tokensPerSecond" data-type="number">Tokens/s</th>
            <th id="score-group-heading" class="group-heading" colspan="1" rowspan="2" data-key="finalScore" data-type="number">Score final</th>
            <th id="temperature-group-heading" class="group-heading" colspan="1" rowspan="2" data-key="selectedTemperature" data-type="number">Best temp</th>
          </tr>
          <tr id="secondary-header-row" hidden>
            <th id="total-token-heading" class="numeric" data-key="totalTokens" data-type="number" hidden>Total</th>
            <th class="numeric" data-key="highestTokenTaskTotalTokens" data-type="number" data-column-group="token" hidden>Max task</th>
            <th data-key="highestTokenTaskId" data-type="text" data-column-group="token" hidden>Task</th>
            <th class="numeric" data-key="easyScore" data-type="number" data-column-group="score" hidden>Easy</th>
            <th class="numeric" data-key="mediumScore" data-type="number" data-column-group="score" hidden>Medium</th>
            <th class="numeric" data-key="hardScore" data-type="number" data-column-group="score" hidden>Hard</th>
            <th id="final-score-heading" class="numeric" data-key="finalScore" data-type="number" hidden>Final</th>
            <th id="selected-temperature-heading" class="numeric" data-key="selectedTemperature" data-type="number" hidden>Best</th>
            {temperature_header_cells}
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
      <div class="empty" id="empty">No benchmark runs match the current filters.</div>
    </div>

    <section class="chart-section" aria-label="Final score chart">
      <div class="chart-header">
        <h2>Final Score</h2>
        <span id="chart-count"></span>
      </div>
      <div class="score-chart" id="score-chart"></div>
    </section>

    <section class="chart-section" aria-label="Final score by total time chart">
      <div class="chart-header">
        <h2>Score vs Time</h2>
        <span id="tradeoff-count"></span>
      </div>
      <div class="tradeoff-chart">
        <div class="tradeoff-plot" id="tradeoff-plot"></div>
        <div class="tradeoff-legend" id="tradeoff-legend"></div>
      </div>
    </section>
  </main>

  <script>
    const table = document.querySelector("#results-table");
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const filters = {{
      search: document.querySelector("#search"),
      generator: document.querySelector("#generator"),
      company: document.querySelector("#company"),
      quantization: document.querySelector("#quantization"),
    }};
    const scoreRange = {{
      minInput: document.querySelector("#min-score"),
      maxInput: document.querySelector("#max-score"),
      minSlider: document.querySelector("#min-score-slider"),
      maxSlider: document.querySelector("#max-score-slider"),
      fill: document.querySelector("#score-range-fill"),
    }};
    const columnToggles = {{
      token: document.querySelector("#show-token-columns"),
      score: document.querySelector("#show-score-columns"),
      temperature: document.querySelector("#show-temperature-columns"),
    }};
    const visibleCount = document.querySelector("#visible-count");
    const empty = document.querySelector("#empty");
    const reset = document.querySelector("#reset");
    const secondaryHeaderRow = document.querySelector("#secondary-header-row");
    const tokenGroupHeading = document.querySelector("#token-group-heading");
    const scoreGroupHeading = document.querySelector("#score-group-heading");
    const temperatureGroupHeading = document.querySelector("#temperature-group-heading");
    const totalTokenHeading = document.querySelector("#total-token-heading");
    const finalScoreHeading = document.querySelector("#final-score-heading");
    const selectedTemperatureHeading = document.querySelector("#selected-temperature-heading");
    const scoreChart = document.querySelector("#score-chart");
    const chartCount = document.querySelector("#chart-count");
    const tradeoffPlot = document.querySelector("#tradeoff-plot");
    const tradeoffLegend = document.querySelector("#tradeoff-legend");
    const tradeoffCount = document.querySelector("#tradeoff-count");
    const storageKey = `csharp-llm-benchmark:filters:${{window.location.pathname}}`;
    let sortState = {{ key: "rank", direction: "asc", type: "number" }};
    let isRestoringState = false;
    const extremeRules = [
      {{ key: "finalScore", best: "max" }},
      {{ key: "totalSeconds", best: "min" }},
      {{ key: "totalTokens", best: "min" }},
      {{ key: "highestTokenTaskTotalTokens", best: "min" }},
      {{ key: "tokensPerSecond", best: "max" }},
    ];

    function normalize(value) {{
      return (value || "").toString().trim().toLowerCase();
    }}

    function numberValue(row, key) {{
      const value = Number(row.dataset[key]);
      return Number.isFinite(value) ? value : Number.NEGATIVE_INFINITY;
    }}

    function textValue(row, key) {{
      return normalize(row.dataset[key]);
    }}

    function visibleTableRows() {{
      return Array.from(tbody.querySelectorAll("tr")).filter((row) => !row.hidden);
    }}

    function browserStorage() {{
      try {{
        const storage = window.localStorage;
        const testKey = `${{storageKey}}:test`;
        storage.setItem(testKey, "1");
        storage.removeItem(testKey);
        return storage;
      }} catch (_error) {{
        return null;
      }}
    }}

    function readStoredState() {{
      const storage = browserStorage();
      if (storage === null) {{
        return null;
      }}
      try {{
        const value = storage.getItem(storageKey);
        return value ? JSON.parse(value) : null;
      }} catch (_error) {{
        return null;
      }}
    }}

    function selectHasValue(select, value) {{
      return Array.from(select.options).some((option) => option.value === value);
    }}

    function sortHeaderForKey(key) {{
      return Array.from(table.querySelectorAll("th[data-key]"))
        .find((header) => header.dataset.key === key) || null;
    }}

    function saveBrowserState() {{
      if (isRestoringState) {{
        return;
      }}
      const storage = browserStorage();
      if (storage === null) {{
        return;
      }}
      const state = {{
        version: 1,
        filters: {{
          search: filters.search.value,
          generator: filters.generator.value,
          company: filters.company.value,
          quantization: filters.quantization.value,
          minScore: scoreRange.minInput.value,
          maxScore: scoreRange.maxInput.value,
        }},
        columns: {{
          token: columnToggles.token.checked,
          score: columnToggles.score.checked,
          temperature: columnToggles.temperature.checked,
        }},
        sort: sortState,
      }};
      try {{
        storage.setItem(storageKey, JSON.stringify(state));
      }} catch (_error) {{
      }}
    }}

    function restoreBrowserState() {{
      const state = readStoredState();
      if (state === null || typeof state !== "object") {{
        return;
      }}

      isRestoringState = true;
      const storedFilters = state.filters || {{}};
      filters.search.value = typeof storedFilters.search === "string" ? storedFilters.search : "";
      filters.generator.value = selectHasValue(filters.generator, storedFilters.generator) ? storedFilters.generator : "";
      filters.company.value = selectHasValue(filters.company, storedFilters.company) ? storedFilters.company : "";
      filters.quantization.value = selectHasValue(filters.quantization, storedFilters.quantization) ? storedFilters.quantization : "";
      setScoreRange(
        clampScore(storedFilters.minScore, 0),
        clampScore(storedFilters.maxScore, 100),
      );
      syncScoreRange("min", false);

      const storedColumns = state.columns || {{}};
      columnToggles.token.checked = storedColumns.token === true;
      columnToggles.score.checked = storedColumns.score === true;
      columnToggles.temperature.checked = storedColumns.temperature === true;

      const storedSort = state.sort || {{}};
      const sortHeader = sortHeaderForKey(storedSort.key);
      if (
        sortHeader !== null &&
        (storedSort.direction === "asc" || storedSort.direction === "desc")
      ) {{
        sortState = {{
          key: storedSort.key,
          direction: storedSort.direction,
          type: storedSort.type === "text" ? "text" : "number",
        }};
      }}
      isRestoringState = false;
    }}

    function formatDurationLabel(totalSeconds) {{
      const seconds = Math.max(0, Math.round(totalSeconds));
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      const remainingSeconds = seconds % 60;
      return `${{hours.toString().padStart(2, "0")}}:${{minutes.toString().padStart(2, "0")}}:${{remainingSeconds.toString().padStart(2, "0")}}`;
    }}

    function clampScore(value, fallback) {{
      const number = Number(value);
      if (!Number.isFinite(number)) {{
        return fallback;
      }}
      return Math.max(0, Math.min(100, number));
    }}

    function formatScoreInput(value) {{
      return Number.isInteger(value) ? value.toString() : value.toFixed(2).replace(/0+$/, "").replace(/\\.$/, "");
    }}

    function setScoreRange(minScore, maxScore) {{
      scoreRange.minInput.value = formatScoreInput(minScore);
      scoreRange.maxInput.value = formatScoreInput(maxScore);
      scoreRange.minSlider.value = minScore;
      scoreRange.maxSlider.value = maxScore;
      scoreRange.fill.style.left = `${{minScore}}%`;
      scoreRange.fill.style.right = `${{100 - maxScore}}%`;
    }}

    function syncScoreRange(changedSide, shouldApply = true) {{
      let minScore = clampScore(scoreRange.minInput.value, 0);
      let maxScore = clampScore(scoreRange.maxInput.value, 100);

      if (changedSide === "min" && minScore > maxScore) {{
        maxScore = minScore;
      }} else if (changedSide === "max" && maxScore < minScore) {{
        minScore = maxScore;
      }} else if (minScore > maxScore) {{
        const previousMin = minScore;
        minScore = maxScore;
        maxScore = previousMin;
      }}

      setScoreRange(minScore, maxScore);
      if (shouldApply) {{
        applyFilters();
      }}
    }}

    function rowMatches(row) {{
      const query = normalize(filters.search.value);
      const generator = filters.generator.value;
      const company = filters.company.value;
      const quantization = filters.quantization.value;
      const minScore = clampScore(scoreRange.minInput.value, 0);
      const maxScore = clampScore(scoreRange.maxInput.value, 100);

      if (query && !normalize(row.dataset.search).includes(query)) {{
        return false;
      }}
      if (generator && row.dataset.generator !== generator) {{
        return false;
      }}
      if (company && row.dataset.company !== company) {{
        return false;
      }}
      if (quantization && row.dataset.quantization !== quantization) {{
        return false;
      }}
      const finalScore = numberValue(row, "finalScore");
      if (finalScore < minScore || finalScore > maxScore) {{
        return false;
      }}
      return true;
    }}

    function toggleModelSearch(model) {{
      filters.search.value = filters.search.value.trim() === model ? "" : model;
      applyFilters();
      filters.search.focus();
    }}

    function clearExtremes() {{
      table.querySelectorAll("[data-extreme-key]").forEach((cell) => {{
        cell.classList.remove("extreme-best", "extreme-worst");
      }});
    }}

    function applyExtremes() {{
      clearExtremes();
      const visibleRows = rows.filter((row) => !row.hidden);
      if (visibleRows.length < 2) {{
        return;
      }}

      for (const rule of extremeRules) {{
        const cells = [];
        for (const row of visibleRows) {{
          const value = Number(row.dataset[rule.key]);
          const cell = row.querySelector(`[data-extreme-key="${{rule.key}}"]`);
          if (!cell || cell.hidden || !Number.isFinite(value)) {{
            continue;
          }}
          cells.push({{ cell, value }});
        }}

        if (cells.length < 2) {{
          continue;
        }}

        const values = cells.map((item) => item.value);
        const min = Math.min(...values);
        const max = Math.max(...values);
        if (min === max) {{
          continue;
        }}

        const bestValue = rule.best === "max" ? max : min;
        const worstValue = rule.best === "max" ? min : max;
        for (const item of cells) {{
          if (item.value === bestValue) {{
            item.cell.classList.add("extreme-best");
          }}
          if (item.value === worstValue) {{
            item.cell.classList.add("extreme-worst");
          }}
        }}
      }}
    }}

    function applyFilters() {{
      let visible = 0;
      for (const row of rows) {{
        const matches = rowMatches(row);
        row.hidden = !matches;
        if (matches) visible += 1;
      }}
      visibleCount.textContent = `Showing ${{visible}} of ${{rows.length}} runs`;
      empty.style.display = visible === 0 ? "block" : "none";
      applyExtremes();
      renderScoreChart();
      renderTradeoffChart();
      saveBrowserState();
    }}

    function applySort() {{
      const multiplier = sortState.direction === "asc" ? 1 : -1;
      const sortedRows = [...rows].sort((a, b) => {{
        if (sortState.type === "number") {{
          return (numberValue(a, sortState.key) - numberValue(b, sortState.key)) * multiplier;
        }}
        return textValue(a, sortState.key).localeCompare(textValue(b, sortState.key)) * multiplier;
      }});
      for (const row of sortedRows) {{
        tbody.appendChild(row);
      }}
      applyExtremes();
      renderScoreChart();
      renderTradeoffChart();
      saveBrowserState();
    }}

    function renderScoreChart() {{
      const visibleRows = visibleTableRows();
      const chartRows = visibleRows
        .map((row) => {{
          const score = Number(row.dataset.finalScore);
          return {{
            generator: row.dataset.generator || "",
            model: row.dataset.model || "n/a",
            quantization: row.dataset.quantization || "",
            score: Number.isFinite(score) ? score : null,
          }};
        }})
        .filter((row) => row.score !== null);

      scoreChart.replaceChildren();
      chartCount.textContent = `${{chartRows.length}} visible runs`;

      if (chartRows.length === 0) {{
        const emptyChart = document.createElement("div");
        emptyChart.className = "empty";
        emptyChart.style.display = "block";
        emptyChart.textContent = "No final scores match the current filters.";
        scoreChart.appendChild(emptyChart);
        return;
      }}

      for (const row of chartRows) {{
        const modelText = row.model;
        const quantText = row.quantization && row.quantization !== "-" ? row.quantization : "";
        const generatorText = row.generator || "";
        const label = [modelText, quantText, generatorText].filter(Boolean).join(" · ");
        const score = Math.max(0, Math.min(100, row.score));

        const chartRow = document.createElement("div");
        chartRow.className = "chart-row";

        const labelElement = document.createElement("div");
        labelElement.className = "chart-label";
        labelElement.title = label;

        const modelCell = document.createElement("span");
        modelCell.className = "chart-model";
        modelCell.title = modelText;
        modelCell.textContent = modelText;

        const quantCell = document.createElement("span");
        quantCell.className = "chart-quant";
        quantCell.title = quantText;
        quantCell.textContent = quantText;

        const generatorCell = document.createElement("span");
        generatorCell.className = "chart-generator";
        generatorCell.title = generatorText;
        generatorCell.textContent = generatorText;

        labelElement.append(modelCell, quantCell, generatorCell);

        const track = document.createElement("div");
        track.className = "chart-track";
        track.setAttribute("aria-label", `${{label}} final score ${{row.score.toFixed(2)}}`);

        const bar = document.createElement("div");
        bar.className = "chart-bar";
        bar.style.width = `${{score}}%`;
        track.appendChild(bar);

        const value = document.createElement("div");
        value.className = "chart-value";
        value.textContent = row.score.toFixed(2);

        chartRow.append(labelElement, track, value);
        scoreChart.appendChild(chartRow);
      }}
    }}

    function renderTradeoffChart() {{
      const chartRows = visibleTableRows()
        .map((row) => {{
          const score = Number(row.dataset.finalScore);
          const totalSeconds = Number(row.dataset.totalSeconds);
          return {{
            model: row.dataset.model || "n/a",
            quantization: row.dataset.quantization || "n/a",
            color: row.dataset.seriesColor || "#64748b",
            score: Number.isFinite(score) ? score : null,
            totalSeconds: Number.isFinite(totalSeconds) ? totalSeconds : null,
          }};
        }})
        .filter((row) => row.score !== null && row.totalSeconds !== null);

      tradeoffPlot.replaceChildren();
      tradeoffLegend.replaceChildren();
      tradeoffCount.textContent = `${{chartRows.length}} visible runs`;

      if (chartRows.length === 0) {{
        const emptyChart = document.createElement("div");
        emptyChart.className = "empty";
        emptyChart.style.display = "block";
        emptyChart.textContent = "No score/time data match the current filters.";
        tradeoffPlot.appendChild(emptyChart);
        return;
      }}

      const minSeconds = Math.min(...chartRows.map((row) => row.totalSeconds));
      const maxSeconds = Math.max(...chartRows.map((row) => row.totalSeconds));
      const minScore = Math.min(...chartRows.map((row) => row.score));
      const maxScore = Math.max(...chartRows.map((row) => row.score));
      const secondRange = maxSeconds - minSeconds || 1;
      const scoreRange = maxScore - minScore || 1;
      const scale = (value, min, max, range) => max === min ? 50 : ((value - min) / range) * 100;

      const plotInner = document.createElement("div");
      plotInner.className = "tradeoff-inner";

      const xLabel = document.createElement("div");
      xLabel.className = "axis-label axis-label-x";
      xLabel.textContent = "Total time";

      const yLabel = document.createElement("div");
      yLabel.className = "axis-label axis-label-y";
      yLabel.textContent = "Final score";

      const xMin = document.createElement("div");
      xMin.className = "axis-value axis-x-min";
      xMin.textContent = formatDurationLabel(minSeconds);

      const xMax = document.createElement("div");
      xMax.className = "axis-value axis-x-max";
      xMax.textContent = formatDurationLabel(maxSeconds);

      const yMin = document.createElement("div");
      yMin.className = "axis-value axis-y-min";
      yMin.textContent = minScore.toFixed(2);

      const yMax = document.createElement("div");
      yMax.className = "axis-value axis-y-max";
      yMax.textContent = maxScore.toFixed(2);

      for (const row of chartRows) {{
        const label = row.quantization && row.quantization !== "-"
          ? `${{row.model}} (${{row.quantization}})`
          : row.model;
        const point = document.createElement("button");
        point.className = "scatter-point";
        point.type = "button";
        point.style.left = `${{scale(row.totalSeconds, minSeconds, maxSeconds, secondRange)}}%`;
        point.style.bottom = `${{scale(row.score, minScore, maxScore, scoreRange)}}%`;
        point.style.setProperty("--point-color", row.color);
        point.title = `${{label}}: score ${{row.score.toFixed(2)}}, time ${{formatDurationLabel(row.totalSeconds)}}`;
        point.setAttribute("aria-label", point.title);
        point.addEventListener("click", () => toggleModelSearch(row.model));
        plotInner.appendChild(point);
      }}

      tradeoffPlot.append(plotInner, xLabel, yLabel, xMin, xMax, yMin, yMax);

      const legendItems = new Map();
      for (const row of chartRows) {{
        if (!legendItems.has(row.quantization)) {{
          legendItems.set(row.quantization, row.color);
        }}
      }}

      for (const [label, color] of legendItems) {{
        const item = document.createElement("div");
        item.className = "legend-item";

        const dot = document.createElement("span");
        dot.className = "legend-dot";
        dot.style.setProperty("--point-color", color);

        const text = document.createElement("span");
        text.textContent = label || "n/a";

        item.append(dot, text);
        tradeoffLegend.appendChild(item);
      }}
    }}

    function updateSortIndicators(activeHeader) {{
      table.querySelectorAll("th").forEach((header) => {{
        header.removeAttribute("data-sort-active");
      }});
      activeHeader.dataset.sortActive = sortState.direction;
    }}

    function applyColumnVisibility() {{
      const showTokenColumns = columnToggles.token.checked;
      const showScoreColumns = columnToggles.score.checked;
      const showTemperatureColumns = columnToggles.temperature.checked;

      table.querySelectorAll('[data-column-group="token"]').forEach((cell) => {{
        cell.hidden = !showTokenColumns;
      }});
      table.querySelectorAll('[data-column-group="score"]').forEach((cell) => {{
        cell.hidden = !showScoreColumns;
      }});
      table.querySelectorAll('[data-column-group="temperature"]').forEach((cell) => {{
        cell.hidden = !showTemperatureColumns;
      }});

      secondaryHeaderRow.hidden = !showTokenColumns && !showScoreColumns && !showTemperatureColumns;

      tokenGroupHeading.textContent = showTokenColumns ? "Tokens" : "Total tokens";
      tokenGroupHeading.colSpan = showTokenColumns ? 3 : 1;
      tokenGroupHeading.rowSpan = showTokenColumns ? 1 : 2;
      tokenGroupHeading.dataset.expanded = showTokenColumns ? "true" : "false";
      totalTokenHeading.hidden = !showTokenColumns;

      scoreGroupHeading.textContent = showScoreColumns ? "Score" : "Score final";
      scoreGroupHeading.colSpan = showScoreColumns ? 4 : 1;
      scoreGroupHeading.rowSpan = showScoreColumns ? 1 : 2;
      scoreGroupHeading.dataset.expanded = showScoreColumns ? "true" : "false";
      finalScoreHeading.hidden = !showScoreColumns;

      const temperatureColumnCount = table.querySelectorAll('thead [data-column-group="temperature"]').length;
      temperatureGroupHeading.textContent = showTemperatureColumns ? "Temperature" : "Best temp";
      temperatureGroupHeading.colSpan = showTemperatureColumns ? temperatureColumnCount + 1 : 1;
      temperatureGroupHeading.rowSpan = showTemperatureColumns ? 1 : 2;
      temperatureGroupHeading.dataset.expanded = showTemperatureColumns ? "true" : "false";
      selectedTemperatureHeading.hidden = !showTemperatureColumns;
      applyExtremes();
      saveBrowserState();
    }}

    for (const input of Object.values(filters)) {{
      input.addEventListener("input", applyFilters);
      input.addEventListener("change", applyFilters);
    }}

    scoreRange.minInput.addEventListener("change", () => syncScoreRange("min"));
    scoreRange.maxInput.addEventListener("change", () => syncScoreRange("max"));
    scoreRange.minSlider.addEventListener("input", () => {{
      scoreRange.minInput.value = scoreRange.minSlider.value;
      syncScoreRange("min");
    }});
    scoreRange.maxSlider.addEventListener("input", () => {{
      scoreRange.maxInput.value = scoreRange.maxSlider.value;
      syncScoreRange("max");
    }});

    for (const toggle of Object.values(columnToggles)) {{
      toggle.addEventListener("change", applyColumnVisibility);
    }}

    tbody.addEventListener("click", (event) => {{
      const button = event.target.closest("[data-model-filter]");
      if (button === null) {{
        return;
      }}
      toggleModelSearch(button.dataset.modelFilter || "");
    }});

    table.querySelectorAll("th[data-key]").forEach((header) => {{
      header.addEventListener("click", () => {{
        if (header.classList.contains("group-heading") && header.rowSpan !== 2) {{
          return;
        }}
        const key = header.dataset.key;
        const type = header.dataset.type || "text";
        const direction = sortState.key === key && sortState.direction === "asc" ? "desc" : "asc";
        sortState = {{ key, type, direction }};
        applySort();
        updateSortIndicators(header);
      }});
    }});

    reset.addEventListener("click", () => {{
      filters.search.value = "";
      filters.generator.value = "";
      filters.company.value = "";
      filters.quantization.value = "";
      setScoreRange(0, 100);
      saveBrowserState();
      applyFilters();
    }});

    setScoreRange(0, 100);
    restoreBrowserState();
    applyColumnVisibility();
    applySort();
    updateSortIndicators(sortHeaderForKey(sortState.key) || sortHeaderForKey("rank"));
    applyFilters();
  </script>
</body>
</html>
"""


def render_html_row(
    rank: int,
    result: BenchmarkResult,
    quantization_colors: dict[str, dict[str, str]],
    temperature_columns: list[tuple[str, str]],
) -> str:
    easy_score = result.difficulty_scores["easy"]
    medium_score = result.difficulty_scores["medium"]
    hard_score = result.difficulty_scores["hard"]
    quantization_label = result.quantization or "n/a"
    quantization_cell = render_quantization_cell(
        quantization_label,
        quantization_colors,
    )
    series_color = quantization_colors[quantization_label]["bg"]
    temperature_data_attrs = render_temperature_data_attrs(
        result,
        temperature_columns,
    )
    temperature_cells = render_temperature_score_cells(result, temperature_columns)
    search_text = " ".join(
        [
            str(rank),
            result.generator,
            result.model,
            result.company,
            result.quantization,
            result.highest_token_task_id or "",
            format_duration(result.total_seconds),
            format_int(result.total_tokens),
            format_int(result.highest_token_task_total_tokens),
            format_number(result.tokens_per_second),
            format_score(easy_score),
            format_score(medium_score),
            format_score(hard_score),
            format_score(result.final_score),
            format_temperature(result.selected_temperature),
            *(
                format_score(result.temperature_scores.get(label))
                for label, _key in temperature_columns
            ),
        ]
    )
    return (
        "          <tr "
        f'data-rank="{rank}" '
        f'data-generator="{escape_attr(result.generator)}" '
        f'data-model="{escape_attr(result.model)}" '
        f'data-company="{escape_attr(result.company)}" '
        f'data-quantization="{escape_attr(result.quantization)}" '
        f'data-total-seconds="{number_attr(result.total_seconds)}" '
        f'data-total-tokens="{number_attr(result.total_tokens)}" '
        f'data-highest-token-task-total-tokens="{number_attr(result.highest_token_task_total_tokens)}" '
        f'data-highest-token-task-id="{escape_attr(result.highest_token_task_id or "")}" '
        f'data-tokens-per-second="{number_attr(result.tokens_per_second)}" '
        f'data-easy-score="{number_attr(easy_score)}" '
        f'data-medium-score="{number_attr(medium_score)}" '
        f'data-hard-score="{number_attr(hard_score)}" '
        f'data-final-score="{number_attr(result.final_score)}" '
        f'data-selected-temperature="{number_attr(result.selected_temperature)}" '
        f"{temperature_data_attrs}"
        f'data-series-color="{escape_attr(series_color)}" '
        f'data-search="{escape_attr(search_text)}">'
        f'<td class="numeric">{rank}</td>'
        f"<td>{escape_html(result.generator)}</td>"
        f'<td class="model"><button class="model-button" type="button" data-model-filter="{escape_attr(result.model)}">{escape_html(result.model)}</button></td>'
        f'<td>{escape_html(result.company or "n/a")}</td>'
        f"<td>{quantization_cell}</td>"
        f'<td class="numeric" data-extreme-key="totalSeconds">{escape_html(format_duration(result.total_seconds))}</td>'
        f'<td class="numeric" data-extreme-key="totalTokens">{escape_html(format_int(result.total_tokens))}</td>'
        f'<td class="numeric" data-extreme-key="highestTokenTaskTotalTokens" data-column-group="token" hidden>{escape_html(format_int(result.highest_token_task_total_tokens))}</td>'
        f'<td data-column-group="token" hidden>{escape_html(result.highest_token_task_id or "n/a")}</td>'
        f'<td class="numeric" data-extreme-key="tokensPerSecond">{escape_html(format_number(result.tokens_per_second))}</td>'
        f'<td class="numeric" data-column-group="score" hidden>{escape_html(format_score(easy_score))}</td>'
        f'<td class="numeric" data-column-group="score" hidden>{escape_html(format_score(medium_score))}</td>'
        f'<td class="numeric" data-column-group="score" hidden>{escape_html(format_score(hard_score))}</td>'
        f'<td class="numeric" data-extreme-key="finalScore">{escape_html(format_score(result.final_score))}</td>'
        f'<td class="numeric">{escape_html(format_temperature(result.selected_temperature))}</td>'
        f"{temperature_cells}"
        "</tr>"
    )


def render_temperature_header_cells(
    temperature_columns: list[tuple[str, str]],
) -> str:
    return "\n            ".join(
        f'<th class="numeric" data-key="{escape_attr(key)}" data-type="number" data-column-group="temperature" hidden>Temp {escape_html(label)}</th>'
        for label, key in temperature_columns
    )


def render_temperature_data_attrs(
    result: BenchmarkResult,
    temperature_columns: list[tuple[str, str]],
) -> str:
    return "".join(
        f'data-{key}="{number_attr(result.temperature_scores.get(label))}" '
        for label, key in temperature_columns
    )


def render_temperature_score_cells(
    result: BenchmarkResult,
    temperature_columns: list[tuple[str, str]],
) -> str:
    return "".join(
        f'<td class="numeric" data-column-group="temperature" hidden>{escape_html(format_score(result.temperature_scores.get(label)))}</td>'
        for label, _key in temperature_columns
    )


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


def normalize_generator(value: Any) -> str:
    if str(value or "llm").strip().lower() == "opencode":
        return "OpenCode"
    return "LLM"


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


def format_temperature(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:g}"


def build_tag_colors(values: Iterable[str]) -> dict[str, dict[str, str]]:
    colors: dict[str, dict[str, str]] = {}
    for index, value in enumerate(values):
        colors[value] = TAG_COLORS[index % len(TAG_COLORS)]
    return colors


def render_style_attr(color: dict[str, str]) -> str:
    return escape_attr(
        "; ".join(
            [
                f"--tag-bg: {color['bg']}",
                f"--tag-border: {color['border']}",
                f"--tag-text: {color['text']}",
            ]
        )
    )


def render_quantization_cell(
    quantization: str,
    quantization_colors: dict[str, dict[str, str]],
) -> str:
    if quantization == "-":
        return "-"
    tag_style = render_style_attr(quantization_colors[quantization])
    return f'<span class="tag" style="{tag_style}">{escape_html(quantization)}</span>'


def render_options(values: Iterable[str]) -> str:
    return "\n          ".join(
        f'<option value="{escape_attr(value)}">{escape_html(value)}</option>'
        for value in values
    )


def number_attr(value: float | int | None) -> str:
    if value is None:
        return ""
    return str(value)


def escape_html(value: str) -> str:
    return html.escape(value, quote=False)


def escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


def markdown_code(value: str) -> str:
    return "`" + value.replace("`", "\\`").replace("|", "\\|") + "`"


if __name__ == "__main__":
    raise SystemExit(main())
