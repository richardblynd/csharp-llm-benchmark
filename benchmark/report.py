from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark.config import AppConfig
from benchmark.scorer import BenchmarkScore, TaskScore


def create_run_dir(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "tasks").mkdir()
    return run_dir


def write_summary(
    run_dir: Path,
    *,
    config: AppConfig,
    score: BenchmarkScore,
    task_scores: list[TaskScore],
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    total_llm_time = sum(
        task_score.llm_response_time_seconds for task_score in task_scores
    )
    average_llm_time = total_llm_time / len(task_scores) if task_scores else 0.0
    total_prompt_tokens = _sum_known_tokens(
        task_score.llm_usage.prompt_tokens for task_score in task_scores
    )
    total_completion_tokens = _sum_known_tokens(
        task_score.llm_usage.completion_tokens for task_score in task_scores
    )
    total_tokens = _sum_known_tokens(
        task_score.llm_usage.total_tokens for task_score in task_scores
    )
    total_reasoning_tokens = _sum_known_tokens(
        task_score.llm_usage.reasoning_tokens for task_score in task_scores
    )
    highest_token_task = find_highest_token_task(task_scores)
    payload: dict[str, Any] = {
        "generated_at": generated_at,
        "model": config.llm.model,
        "llm": {
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "temperature": config.llm.temperature,
            "seed": config.llm.seed,
            "timeout_seconds": config.llm.timeout_seconds,
        },
        "score": {
            "earned_points": score.earned_points,
            "available_points": score.available_points,
            "final_score": score.final_score,
        },
        "llm_response_time": {
            "total_seconds": total_llm_time,
            "average_seconds": average_llm_time,
        },
        "llm_token_usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "reasoning_tokens": total_reasoning_tokens,
        },
        "highest_token_task": (
            {
                "task_id": highest_token_task.task_id,
                "total_tokens": highest_token_task.llm_usage.total_tokens,
                "llm_response_time_seconds": (
                    highest_token_task.llm_response_time_seconds
                ),
            }
            if highest_token_task is not None
            else None
        ),
        "tasks": [asdict(task_score) for task_score in task_scores],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary.md").write_text(
        _render_markdown(payload),
        encoding="utf-8",
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# C# LLM Benchmark Summary",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Model: `{payload['model']}`",
        f"- Final score: `{payload['score']['final_score']}`",
        f"- Points: `{payload['score']['earned_points']} / {payload['score']['available_points']}`",
        f"- Total LLM response time: `{format_duration_hms(payload['llm_response_time']['total_seconds'])}`",
        f"- Average LLM response time: `{_format_seconds(payload['llm_response_time']['average_seconds'])}`",
        f"- Total LLM tokens: `{_format_tokens(payload['llm_token_usage']['total_tokens'])}`",
        f"- Prompt tokens: `{_format_tokens(payload['llm_token_usage']['prompt_tokens'])}`",
        f"- Completion tokens: `{_format_tokens(payload['llm_token_usage']['completion_tokens'])}`",
        f"- Reasoning tokens: `{_format_tokens(payload['llm_token_usage']['reasoning_tokens'])}`",
        _format_highest_token_task(payload["highest_token_task"]),
        "",
        "| Task | Status | Points | Passed | Failed | LLM time | Tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for task in payload["tasks"]:
        lines.append(
            "| {task_id} | {status} | {earned_points} / {available_points} | {passed} | {failed} | {llm_time} | {tokens} |".format(
                task_id=task["task_id"],
                status=task["status"],
                earned_points=task["earned_points"],
                available_points=task["available_points"],
                passed=len(task["passed_tests"]),
                failed=len(task["failed_tests"]),
                llm_time=_format_seconds(task["llm_response_time_seconds"]),
                tokens=_format_tokens(task["llm_usage"]["total_tokens"]),
            )
        )
    lines.append("")
    return "\n".join(lines)


def find_highest_token_task(task_scores: list[TaskScore]) -> TaskScore | None:
    known_token_scores = [
        task_score
        for task_score in task_scores
        if task_score.llm_usage.total_tokens is not None
    ]
    if not known_token_scores:
        return None
    return max(
        known_token_scores,
        key=lambda task_score: task_score.llm_usage.total_tokens or 0,
    )


def _format_highest_token_task(task: dict[str, Any] | None) -> str:
    if task is None:
        return "- Highest-token task: `unavailable` (token usage unavailable for all tasks)"
    return (
        f"- Highest-token task: `{task['task_id']}` "
        f"(`{task['total_tokens']}` tokens, "
        f"LLM time: `{_format_seconds(task['llm_response_time_seconds'])}`)"
    )


def _format_seconds(seconds: float) -> str:
    return f"{seconds:.2f}s"


def format_duration_hms(seconds: float) -> str:
    total_seconds = int(seconds + 0.5)
    hours, remainder = divmod(total_seconds, 60 * 60)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _sum_known_tokens(values) -> int | None:
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None
    return sum(known_values)


def _format_tokens(tokens: int | None) -> str:
    if tokens is None:
        return "unavailable"
    return str(tokens)
