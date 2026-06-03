from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark.config import AppConfig
from benchmark.scorer import BenchmarkScore, TaskScore


def create_run_dir(output_dir: Path, *, model_label: str, quantization: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = output_dir / "_".join(
        [
            timestamp,
            _format_run_dir_label(model_label),
            _format_run_dir_label(quantization),
        ]
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "tasks").mkdir()
    return run_dir


def write_summary(
    run_dir: Path,
    *,
    config: AppConfig,
    score: BenchmarkScore,
    task_scores: list[TaskScore],
    temperature_scores: list[Any] | None = None,
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
    model_label = config.llm.effective_model_label
    payload: dict[str, Any] = {
        "generated_at": generated_at,
        "generator": config.benchmark.generator,
        "model": config.llm.model,
        "modelLabel": model_label,
        "company": config.llm.company,
        "quantization": config.llm.quantization,
        "llm": {
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "modelLabel": model_label,
            "company": config.llm.company,
            "quantization": config.llm.quantization,
            "temperature": config.llm.temperature,
            "temperatures": list(config.llm.temperatures),
            "top_p": config.llm.top_p,
            "top_k": config.llm.top_k,
            "repetition_penalty": config.llm.repetition_penalty,
            "seed": config.llm.seed,
            "timeout_seconds": config.llm.timeout_seconds,
            "requests_per_minute": config.llm.requests_per_minute,
        },
        "opencode": (
            {
                "version": config.opencode.version,
                "package": config.opencode.package,
                "docker_image": config.opencode.docker_image,
                "cache_dir": str(config.opencode.cache_dir),
                "timeout_seconds": config.opencode.timeout_seconds,
                "keep_timed_out_containers": (
                    config.opencode.keep_timed_out_containers
                ),
                "max_steps": config.opencode.max_steps,
                "network": config.opencode.network,
                "container_base_url": config.opencode.container_base_url,
                "context_limit": config.opencode.context_limit,
                "output_limit": config.opencode.output_limit,
                "compaction": {
                    "auto": config.opencode.compaction_auto,
                    "prune": config.opencode.compaction_prune,
                    "reserved": config.opencode.compaction_reserved,
                },
            }
            if config.benchmark.generator == "opencode"
            else None
        ),
        "score": {
            "earned_points": score.earned_points,
            "available_points": score.available_points,
            "final_score": score.final_score,
        },
        "selected_temperature": config.llm.temperature,
        "temperature_scores": _temperature_scores_payload(temperature_scores),
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


def _temperature_scores_payload(temperature_scores: list[Any] | None) -> list[dict[str, Any]]:
    if not temperature_scores:
        return []

    payloads: list[dict[str, Any]] = []
    for temperature_run in temperature_scores:
        task_scores = list(temperature_run.task_scores)
        score = temperature_run.score
        total_llm_time = sum(
            task_score.llm_response_time_seconds for task_score in task_scores
        )
        highest_token_task = find_highest_token_task(task_scores)
        payloads.append(
            {
                "temperature": temperature_run.temperature,
                "score": {
                    "earned_points": score.earned_points,
                    "available_points": score.available_points,
                    "final_score": score.final_score,
                },
                "llm_response_time": {
                    "total_seconds": total_llm_time,
                    "average_seconds": (
                        total_llm_time / len(task_scores) if task_scores else 0.0
                    ),
                },
                "llm_token_usage": {
                    "prompt_tokens": _sum_known_tokens(
                        task_score.llm_usage.prompt_tokens
                        for task_score in task_scores
                    ),
                    "completion_tokens": _sum_known_tokens(
                        task_score.llm_usage.completion_tokens
                        for task_score in task_scores
                    ),
                    "total_tokens": _sum_known_tokens(
                        task_score.llm_usage.total_tokens
                        for task_score in task_scores
                    ),
                    "reasoning_tokens": _sum_known_tokens(
                        task_score.llm_usage.reasoning_tokens
                        for task_score in task_scores
                    ),
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
        )
    return payloads


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# C# LLM Benchmark Summary",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Generator: `{_format_generator(payload.get('generator'))}`",
        f"- Model label: `{payload['modelLabel']}`",
        f"- Model: `{payload['model']}`",
        f"- Company: `{payload['company'] or 'n/a'}`",
        f"- Quantization: `{payload['quantization']}`",
        f"- Selected temperature: `{_format_temperature(payload['selected_temperature'])}`",
        f"- Configured temperatures: `{_format_temperature_list(payload['llm'].get('temperatures', []))}`",
        f"- Top P: `{payload['llm'].get('top_p')}`",
        f"- Top K: `{payload['llm'].get('top_k')}`",
        f"- Repetition penalty: `{payload['llm'].get('repetition_penalty')}`",
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
        *_render_temperature_table(payload["temperature_scores"]),
        "| Task | Status | Temperature | Points | Passed | Failed | LLM time | Tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for task in payload["tasks"]:
        lines.append(
            "| {task_id} | {status} | {temperature} | {earned_points} / {available_points} | {passed} | {failed} | {llm_time} | {tokens} |".format(
                task_id=task["task_id"],
                status=task["status"],
                temperature=_format_temperature(task.get("temperature")),
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


def _render_temperature_table(temperature_scores: list[dict[str, Any]]) -> list[str]:
    if len(temperature_scores) <= 1:
        return []
    lines = [
        "| Temperature | Final score | Points | Total LLM time | Total tokens |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for temperature_score in temperature_scores:
        score = temperature_score["score"]
        lines.append(
            "| {temperature} | {final_score} | {earned_points} / {available_points} | {total_time} | {tokens} |".format(
                temperature=_format_temperature(temperature_score["temperature"]),
                final_score=score["final_score"],
                earned_points=score["earned_points"],
                available_points=score["available_points"],
                total_time=format_duration_hms(
                    temperature_score["llm_response_time"]["total_seconds"]
                ),
                tokens=_format_tokens(
                    temperature_score["llm_token_usage"]["total_tokens"]
                ),
            )
        )
    lines.append("")
    return lines


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


def _format_run_dir_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip(".-_")
    return cleaned[:80] or "unknown"


def _sum_known_tokens(values) -> int | None:
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None
    return sum(known_values)


def _format_tokens(tokens: int | None) -> str:
    if tokens is None:
        return "unavailable"
    return str(tokens)


def _format_temperature(temperature: Any) -> str:
    if temperature is None:
        return "n/a"
    return f"{float(temperature):g}"


def _format_temperature_list(temperatures: Any) -> str:
    if not isinstance(temperatures, list):
        return "n/a"
    return ", ".join(_format_temperature(temperature) for temperature in temperatures)


def _format_generator(generator: Any) -> str:
    if str(generator or "llm").lower() == "opencode":
        return "OpenCode"
    return "LLM"
