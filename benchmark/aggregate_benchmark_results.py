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
    version: str | None
    model: str
    company: str
    quantization: str
    kv_cache_quantization: str | None
    total_seconds: float | None
    total_tokens: int | None
    highest_token_task_id: str | None
    highest_token_task_total_tokens: int | None
    tokens_per_second: float | None
    difficulty_scores: dict[str, float | None]
    selected_temperature: float | None
    temperature_scores: dict[str, float | None]
    uses_discovery: bool
    context_limit: int
    final_score: float | None
    earned_points: float | None
    available_points: float | None


_GENERATOR_KEY = {"opencode": "OpenCode", "pi": "Pi"}


@dataclass(frozen=True)
class GroupedResult:
    model: str
    company: str
    quantization: str
    kv_cache_quantization: str | None
    context_limit: int
    score_llm: float | None
    score_pi: float | None
    score_opencode: float | None

    def avg_score(self) -> float | None:
        scores = [s for s in (self.score_llm, self.score_pi, self.score_opencode) if s is not None]
        return sum(scores) / len(scores) if scores else None

    def max_score(self) -> float | None:
        scores = [s for s in (self.score_llm, self.score_pi, self.score_opencode) if s is not None]
        return max(scores) if scores else None


def group_results(results: list[BenchmarkResult]) -> list[GroupedResult]:
    groups: dict[tuple[str, ...], list[BenchmarkResult]] = {}

    for r in results:
        gen_label = _GENERATOR_KEY.get(r.generator.lower(), "LLM")
        kv_cache_key = r.kv_cache_quantization or ""
        key = (r.model, r.company, r.quantization, kv_cache_key, r.context_limit)
        groups.setdefault(key, []).append((gen_label, r))

    grouped: list[GroupedResult] = []
    for key, items in groups.items():
        model, company, quantization, kv_cache_key, context_limit = key

        score_map: dict[str, float | None] = {}
        for gen_label, r in items:
            if r.final_score is not None and gen_label not in score_map:
                score_map[gen_label] = r.final_score

        grouped.append(GroupedResult(
            model=model,
            company=company,
            quantization=quantization,
            kv_cache_quantization=None if not kv_cache_key else kv_cache_key,
            context_limit=context_limit,
            score_llm=score_map.get("LLM"),
            score_pi=score_map.get("Pi"),
            score_opencode=score_map.get("OpenCode"),
        ))

    grouped.sort(key=lambda g: (g.avg_score() is not None, g.avg_score() if g.avg_score() is not None else -1.0), reverse=True)
    return grouped


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
    grouped = group_results(benchmark_results)
    markdown = render_markdown(grouped, results_dir)
    output_path.write_text(markdown, encoding="utf-8")
    html_page = render_html(
        grouped,
        results_dir,
    )
    html_output_path.write_text(html_page, encoding="utf-8")

    print(
        f"Wrote {len(grouped)} grouped benchmark results to "
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
    version = (
        str(payload.get("opencode", {}).get("version") or "")
        if generator.lower() == "opencode"
        else str(payload.get("pi", {}).get("version") or "")
        if generator.lower() == "pi"
        else ""
    )
    context_limit_raw = None
    opencode_payload = payload.get("opencode")
    pi_payload = payload.get("pi")
    if isinstance(opencode_payload, dict):
        context_limit_raw = opencode_payload.get("context_limit")
    elif isinstance(pi_payload, dict):
        context_limit_raw = pi_payload.get("context_limit")
    context_limit = int(context_limit_raw) if context_limit_raw is not None else 50000
    company = str(payload.get("company") or llm_payload.get("company") or "")
    quantization = str(
        payload.get("quantization")
        or llm_payload.get("quantization")
        or infer_quantization(run_name)
        or ""
    )

    kv_cache_quantization_raw = (
        payload.get("kv_cache_quantization")
        or llm_payload.get("kv_cache_quantization")
    )
    if kv_cache_quantization_raw is not None and str(kv_cache_quantization_raw).strip():
        kv_cache_quantization: str | None = str(kv_cache_quantization_raw)
    else:
        kv_cache_quantization = None

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
    discovery_info, temperature_scores = parse_temperature_scores(payload)

    tokens_per_second = None
    if total_tokens is not None and total_seconds is not None and total_seconds > 0:
        tokens_per_second = total_tokens / total_seconds

    return BenchmarkResult(
        run_name=run_name,
        generator=generator,
        version=version or None,
        model=model,
        company=company,
        quantization=quantization,
        kv_cache_quantization=kv_cache_quantization,
        total_seconds=total_seconds,
        total_tokens=total_tokens,
        highest_token_task_id=highest_token_task_id,
        highest_token_task_total_tokens=highest_token_task_total_tokens,
        tokens_per_second=tokens_per_second,
        difficulty_scores=difficulty_scores,
        selected_temperature=selected_temperature,
        temperature_scores=temperature_scores,
        uses_discovery=discovery_info.get("enabled", False),
        context_limit=context_limit,
        final_score=final_score,
        earned_points=earned_points,
        available_points=available_points,
    )


def parse_temperature_scores(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, float | None]]:
    """Parse temperature scores from either discovery or legacy format.

    Returns (discovery_info, temperature_scores_dict).
    Discovery info contains {"enabled": bool} to signal which source was used.
    """
    scores: dict[str, float | None] = {}
    discovery_info: dict[str, Any] = {"enabled": False}

    # Prefer discovery.temperature_scores when available (new format)
    discovery_data = payload.get("discovery")
    if isinstance(discovery_data, dict):
        disc_enabled = discovery_data.get("enabled", False)
        disc_temp_scores = discovery_data.get("temperature_scores")
        if disc_enabled and isinstance(disc_temp_scores, list) and disc_temp_scores:
            scores = _extract_temperature_score_map(disc_temp_scores)
            discovery_info["enabled"] = True
            return discovery_info, scores

    # Fallback to legacy top-level temperature_scores (old multi-temp format)
    raw_scores = payload.get("temperature_scores")
    if isinstance(raw_scores, list) and raw_scores:
        scores = _extract_temperature_score_map(raw_scores)

    return discovery_info, scores


def _extract_temperature_score_map(
    entries: list[dict[str, Any]],
) -> dict[str, float | None]:
    """Extract {temp_label: final_score} from a list of temperature score entries.

    Handles both formats:
    - Discovery format: entry has flat `final_score` key
    - Legacy format: entry has nested `score.final_score`
    """
    scores: dict[str, float | None] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        temperature = optional_float(entry.get("temperature"))
        if temperature is None:
            continue
        # Discovery format: flat final_score
        score_value = optional_float(entry.get("final_score"))
        if score_value is None:
            # Legacy format: nested score.final_score
            score_obj = entry.get("score")
            score_value = (
                optional_float(score_obj.get("final_score"))
                if isinstance(score_obj, dict)
                else None
            )
        scores[format_temperature_label(temperature)] = score_value
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


def _format_grouped_score(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"


def render_markdown(
    grouped_results: list[GroupedResult],
    results_dir: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# LLM Benchmark Results",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Results directory: `{results_dir}`",
        f"- Configuration groups: `{len(grouped_results)}`",
        "",
        "| Rank | Model | Company | Quantization | KV Cache | Context Size | SCORE LLM | SCORE PI | SCORE OPENCODE | Avg Score | Max Score |",
        "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for rank, g in enumerate(grouped_results, start=1):
        lines.append(
            f"| {rank} "
            f"| {markdown_code(g.model)} "
            f"| {markdown_code(g.company or 'n/a')} "
            f"| {markdown_code(g.quantization or 'n/a')} "
            f"| {markdown_code(g.kv_cache_quantization or 'n/a')} "
            f"| `{g.context_limit}` "
            f"| {_format_grouped_score(g.score_llm)} "
            f"| {_format_grouped_score(g.score_pi)} "
            f"| {_format_grouped_score(g.score_opencode)} "
            f"| {_format_grouped_score(g.avg_score())} "
            f"| {_format_grouped_score(g.max_score())} |"
        )

    lines.append("")
    return "\n".join(lines)

def render_html_row_grouped(rank: int, g: GroupedResult) -> str:
    avg = g.avg_score()
    mx = g.max_score()
    search_text = " ".join([
        str(rank), g.model, g.company or "", g.quantization or "",
        g.kv_cache_quantization or "", str(g.context_limit),
        _format_grouped_score(g.score_llm),
        _format_grouped_score(g.score_pi),
        _format_grouped_score(g.score_opencode),
        _format_grouped_score(avg),
        _format_grouped_score(mx),
    ])
    return (
        f'      <tr '
        f'data-rank="{rank}" '
        f'data-model="{escape_attr(g.model)}" '
        f'data-company="{escape_attr(g.company or "")}" '
        f'data-quantization="{escape_attr(g.quantization or "")}" '
        f'data-kv-cache-quant="{escape_attr(g.kv_cache_quantization or "")}" '
        f'data-context-limit="{g.context_limit}" '
        f'data-score-llm="{number_attr(g.score_llm)}" '
        f'data-score-pi="{number_attr(g.score_pi)}" '
        f'data-score-opencode="{number_attr(g.score_opencode)}" '
        f'data-avg-score="{number_attr(avg)}" '
        f'data-max-score="{number_attr(mx)}" '
        f'data-search="{escape_attr(search_text)}">'
        f'<td class="numeric">{rank}</td>'
        f'<td class="model"><button class="model-button" type="button" data-model-filter="{escape_attr(g.model)}">{escape_html(g.model)}</button></td>'
        f'<td>{escape_html(g.company or "n/a")}</td>'
        f'<td>{escape_html(g.quantization or "n/a")}</td>'
        f'<td>{escape_html(g.kv_cache_quantization or "n/a")}</td>'
        f'<td class="numeric">{g.context_limit}</td>'
        f'<td class="numeric" data-extreme-key="scoreLlm">{_format_grouped_score(g.score_llm)}</td>'
        f'<td class="numeric" data-extreme-key="scorePi">{_format_grouped_score(g.score_pi)}</td>'
        f'<td class="numeric" data-extreme-key="scoreOpencode">{_format_grouped_score(g.score_opencode)}</td>'
        f'<td class="numeric" data-extreme-key="avgScore">{_format_grouped_score(avg)}</td>'
        f'<td class="numeric" data-extreme-key="maxScore">{_format_grouped_score(mx)}</td>'
        '</tr>'
    )


def render_html(
    grouped_results: list[GroupedResult],
    results_dir: Path,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    companies = sorted({g.company for g in grouped_results if g.company})
    quantizations = sorted({g.quantization for g in grouped_results if g.quantization})
    kv_cache_quantizations = sorted(
        {str(g.kv_cache_quantization) for g in grouped_results if g.kv_cache_quantization is not None}
    )

    rows_html = "\n".join(
        render_html_row_grouped(rank, g)
        for rank, g in enumerate(grouped_results, start=1)
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
      --sidebar-width: 280px;
      --sidebar-collapsed: 32px;
      --header-height: 100px;
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

    * {{ box-sizing: border-box; }}

    html, body {{
      height: 100%;
      margin: 0;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.45;
      overflow: hidden;
    }}

    main {{
      display: flex;
      flex-direction: column;
      height: 100vh;
      max-width: 100%;
    }}

    .header {{
      flex-shrink: 0;
      padding: 24px 32px 16px;
    }}

    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      font-weight: 700;
    }}

    .meta {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}

    .layout-body {{
      display: flex;
      flex: 1;
      overflow: hidden;
      padding: 0 32px 32px;
    }}

    .sidebar {{
      position: relative;
      width: var(--sidebar-width);
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      gap: 14px;
      padding: 0 8px 0 0;
      overflow-y: auto;
      transition: width 0.2s ease, opacity 0.2s ease;
    }}

    .sidebar.collapsed {{
      width: var(--sidebar-collapsed);
      overflow: hidden;
    }}

    .sidebar.collapsed > .sidebar-filters {{
      display: none;
    }}

    .sidebar-filters {{
      display: flex;
      flex-direction: column;
      gap: 14px;
      flex: 1;
      min-height: 0;
      overflow-y: auto;
    }}

    .sidebar-toggle {{
      flex-shrink: 0;
      align-self: flex-end;
      width: 28px;
      height: 28px;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
      line-height: 1;
      padding: 0;
      min-height: auto;
    }}

    .sidebar.collapsed > .sidebar-toggle {{
      align-self: center;
      margin-bottom: 8px;
    }}

    .sidebar-toggle:hover {{
      color: var(--accent);
      border-color: var(--accent);
    }}

    label {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}

    input, select {{
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

    .score-range {{ gap: 8px; }}

    .range-fields {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}

    .range-slider {{
      position: relative;
      --range-thumb-size: 18px;
      --range-track-height: 4px;
      height: 26px;
    }}

    .range-base, .range-fill {{
      position: absolute;
      top: 50%;
      right: 0; left: 0;
      height: var(--range-track-height);
      border-radius: 999px;
      transform: translateY(-50%);
    }}

    .range-base {{ background: color-mix(in srgb, var(--line) 82%, var(--text) 18%); }}
    .range-fill {{ background: var(--accent); }}

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

    .range-slider input::-webkit-slider-runnable-track,
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

    .table-area {{
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
      overflow: hidden;
    }}

    .summary {{
      flex-shrink: 0;
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
      flex: 1;
      min-height: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow-y: auto;
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}

    th, td {{
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

    th[data-key]::after {{
      content: " <>";
      color: var(--muted);
      font-weight: 400;
    }}

    th[data-key][data-sort-active="asc"]::after {{ content: " ^"; color: var(--accent); }}
    th[data-key][data-sort-active="desc"]::after {{ content: " v"; color: var(--accent); }}

    td.numeric, th.numeric {{ text-align: right; }}

    tbody tr:hover {{ background: rgb(23 107 135 / 8%); }}

    td.extreme-best, td.extreme-worst {{
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

    .model {{ font-weight: 700; }}

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

    .empty {{
      display: none;
      padding: 24px;
      color: var(--muted);
      text-align: center;
    }}

    .sidebar-overlay {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgb(0 0 0 / 40%);
      z-index: 8;
    }}

    @media (max-width: 900px) {{
      .header {{ padding: 20px 16px 12px; }}
      .layout-body {{ padding: 0 16px 16px; }}
      .summary {{ display: grid; }}
    }}

    @media (max-width: 599px) {{
      .header {{ padding-top: var(--sidebar-collapsed); }}
      .sidebar {{
        position: fixed;
        top: 0;
        left: 0;
        width: var(--sidebar-width);
        height: 100vh;
        background: var(--panel);
        z-index: 10;
        padding: 48px 16px 16px;
        box-shadow: var(--shadow);
      }}
      .sidebar.collapsed {{
        width: var(--sidebar-collapsed);
      }}
      .sidebar-overlay.active {{ display: block; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="header">
      <h1>LLM Benchmark Results</h1>
      <p class="meta">
        Generated at <code>{escape_html(generated_at)}</code> from
        <code>{escape_html(str(results_dir))}</code>.
      </p>
    </div>

    <div class="layout-body">
      <aside class="sidebar" id="sidebar" aria-label="Table filters">
        <div class="sidebar-filters">
          <label>
            Search
            <input id="search" type="search" placeholder="Model, company, quantization...">
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
          <label>
            KV cache
            <select id="kvCacheQuant">
              <option value="">All KV caches</option>
            {render_options(kv_cache_quantizations)}
          </select>
        </label>
        <label class="score-range">
          Avg score range
          <span class="range-fields">
            <input id="min-score" type="number" min="0" max="100" step="0.1" value="0" aria-label="Minimum avg score">
            <input id="max-score" type="number" min="0" max="100" step="0.1" value="100" aria-label="Maximum avg score">
          </span>
          <span class="range-slider" aria-hidden="true">
            <span class="range-base"></span>
            <span class="range-fill" id="score-range-fill"></span>
            <input id="min-score-slider" type="range" min="0" max="100" step="0.1" value="0" tabindex="-1">
            <input id="max-score-slider" type="range" min="0" max="100" step="0.1" value="100" tabindex="-1">
          </span>
        </label>
        </div>
        <button class="sidebar-toggle" id="sidebar-toggle" aria-label="Toggle filters">◀</button>
      </aside>

      <div class="table-area">
        <div class="summary">
          <span id="visible-count">Showing {len(grouped_results)} of {len(grouped_results)} groups</span>
          <button id="reset" type="button">Reset filters</button>
        </div>
        <div class="table-wrap">
          <table id="results-table">
            <thead>
              <tr>
                <th class="numeric" data-key="rank" data-type="number">Rank</th>
                <th data-key="model" data-type="text">Model</th>
                <th data-key="company" data-type="text">Company</th>
                <th data-key="quantization" data-type="text">Quantization</th>
                <th data-key="kvCacheQuant" data-type="text">KV Cache</th>
                <th class="numeric" data-key="contextLimit" data-type="number">Context Size</th>
                <th class="numeric" data-key="scoreLlm" data-type="number">Score LLM</th>
                <th class="numeric" data-key="scorePi" data-type="number">Score Pi</th>
                <th class="numeric" data-key="scoreOpencode" data-type="number">Score OpenCode</th>
                <th class="numeric" data-key="avgScore" data-type="number">Avg Score</th>
                <th class="numeric" data-key="maxScore" data-type="number">Max Score</th>
              </tr>
            </thead>
            <tbody>
{rows_html}
            </tbody>
          </table>
          <div class="empty" id="empty">No configuration groups match the current filters.</div>
        </div>
      </div>
    </div>

    <div class="sidebar-overlay" id="sidebar-overlay"></div>
  </main>

  <script>
    (function() {{
      const sidebar = document.querySelector("#sidebar");
      const chevron = document.querySelector("#sidebar-toggle");
      const overlay = document.querySelector("#sidebar-overlay");
      const sidebarKey = "csharp-llm-benchmark:sidebar";

      function setCollapsed(collapsed) {{
        sidebar.classList.toggle("collapsed", collapsed);
        chevron.textContent = collapsed ? "\u25B6" : "\u25C0";
        localStorage.setItem(sidebarKey, collapsed ? "1" : "0");
        if (collapsed) {{
          overlay.classList.remove("active");
        }}
      }}

      const saved = localStorage.getItem(sidebarKey);
      if (saved === "1") setCollapsed(true);

      chevron.addEventListener("click", () => {{
        const collapsed = sidebar.classList.contains("collapsed");
        if (!collapsed && window.innerWidth < 600) {{
          overlay.classList.add("active");
        }}
        setCollapsed(!collapsed);
      }});

      overlay.addEventListener("click", () => setCollapsed(true));

    }})();

    const table = document.querySelector("#results-table");
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const filters = {{
      search: document.querySelector("#search"),
      company: document.querySelector("#company"),
      quantization: document.querySelector("#quantization"),
      kvCacheQuant: document.querySelector("#kvCacheQuant"),
    }};
    const scoreRange = {{
      minInput: document.querySelector("#min-score"),
      maxInput: document.querySelector("#max-score"),
      minSlider: document.querySelector("#min-score-slider"),
      maxSlider: document.querySelector("#max-score-slider"),
      fill: document.querySelector("#score-range-fill"),
    }};
    const visibleCount = document.querySelector("#visible-count");
    const emptyEl = document.querySelector("#empty");
    const resetBtn = document.querySelector("#reset");
    const storageKey = `csharp-llm-benchmark:filters:${{window.location.pathname}}`;
    let sortState = {{ key: "avgScore", direction: "desc", type: "number" }};

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

    function clampScore(value, fallback) {{
      const number = Number(value);
      if (!Number.isFinite(number)) return fallback;
      return Math.max(0, Math.min(100, number));
    }}

    function formatScoreInput(value) {{
      const v = Number(value);
      return Number.isInteger(v) ? v.toString() : v.toFixed(1).replace(/\\.0$/, "");
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
      if (changedSide === "min" && minScore > maxScore) maxScore = minScore;
      else if (changedSide === "max" && maxScore < minScore) minScore = maxScore;
      setScoreRange(minScore, maxScore);
      if (shouldApply) applyFilters();
    }}

    function rowMatches(row) {{
      const query = normalize(filters.search.value);
      const company = filters.company.value;
      const quantization = filters.quantization.value;
      const kvCacheQuant = filters.kvCacheQuant.value;
      const minScore = clampScore(scoreRange.minInput.value, 0);
      const maxScore = clampScore(scoreRange.maxInput.value, 100);

      if (query && !normalize(row.dataset.search).includes(query)) return false;
      if (company && row.dataset.company !== company) return false;
      if (quantization && row.dataset.quantization !== quantization) return false;
      if (kvCacheQuant && row.dataset.kvCacheQuant !== kvCacheQuant) return false;
      const avgScore = numberValue(row, "avgScore");
      if (avgScore < minScore || avgScore > maxScore) return false;
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
      if (visibleRows.length < 2) return;

      const extremeRules = [
        {{ key: "avgScore", best: "max" }},
        {{ key: "maxScore", best: "max" }},
        {{ key: "scoreLlm", best: "max" }},
        {{ key: "scorePi", best: "max" }},
        {{ key: "scoreOpencode", best: "max" }},
      ];

      for (const rule of extremeRules) {{
        const cells = [];
        for (const row of visibleRows) {{
          const value = Number(row.dataset[rule.key]);
          if (!Number.isFinite(value)) continue;
          const cell = row.querySelector(`[data-extreme-key="${{rule.key}}"]`);
          if (!cell) continue;
          cells.push({{ cell, value }});
        }}
        if (cells.length < 2) continue;
        const values = cells.map((item) => item.value);
        const min = Math.min(...values);
        const max = Math.max(...values);
        if (min === max) continue;
        const bestValue = rule.best === "max" ? max : min;
        const worstValue = rule.best === "max" ? min : max;
        for (const item of cells) {{
          if (item.value === bestValue) item.cell.classList.add("extreme-best");
          if (item.value === worstValue) item.cell.classList.add("extreme-worst");
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
      visibleCount.textContent = `Showing ${{visible}} of ${{rows.length}} groups`;
      emptyEl.style.display = visible === 0 ? "block" : "none";
      applyExtremes();
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
    }}

    function updateSortIndicators(activeHeader) {{
      table.querySelectorAll("th").forEach((header) => {{
        header.removeAttribute("data-sort-active");
      }});
      activeHeader.dataset.sortActive = sortState.direction;
    }}

    function sortHeaderForKey(key) {{
      return Array.from(table.querySelectorAll("th[data-key]"))
        .find((header) => header.dataset.key === key) || null;
    }}

    // Event listeners
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

    tbody.addEventListener("click", (event) => {{
      const button = event.target.closest("[data-model-filter]");
      if (button === null) return;
      toggleModelSearch(button.dataset.modelFilter || "");
    }});

    table.querySelectorAll("th[data-key]").forEach((header) => {{
      header.addEventListener("click", () => {{
        const key = header.dataset.key;
        const type = header.dataset.type || "text";
        const direction = sortState.key === key && sortState.direction === "asc" ? "desc" : "asc";
        sortState = {{ key, type, direction }};
        applySort();
        updateSortIndicators(header);
      }});
    }});

    resetBtn.addEventListener("click", () => {{
      filters.search.value = "";
      filters.company.value = "";
      filters.quantization.value = "";
      filters.kvCacheQuant.value = "";
      setScoreRange(0, 100);
      applyFilters();
    }});

    // Init: sort by avgScore desc (default)
    setScoreRange(0, 100);
    applySort();
    updateSortIndicators(sortHeaderForKey("avgScore"));
    applyFilters();
  </script>
</body>
</html>
"""


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
    text = str(value or "llm").strip().lower()
    if text == "opencode":
        return "OpenCode"
    if text == "pi":
        return "Pi"
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
