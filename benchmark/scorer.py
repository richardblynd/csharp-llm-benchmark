from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from benchmark.llm_client import LlmUsage
from benchmark.runner import TaskRunResult
from benchmark.tasks import Task


@dataclass(frozen=True)
class TaskScore:
    task_id: str
    status: str
    llm_response_time_seconds: float
    llm_usage: LlmUsage
    earned_points: float
    available_points: float
    compile_points: float
    earned_test_points: float
    passed_tests: tuple[str, ...]
    failed_tests: tuple[str, ...]
    generator: str = "llm"
    opencode_metadata: dict[str, Any] | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class BenchmarkScore:
    earned_points: float
    available_points: float
    final_score: float
    task_scores: tuple[TaskScore, ...]


def score_task(task: Task, result: TaskRunResult) -> TaskScore:
    available = task.score.available_points

    # Non-passing terminal states earn 0 but always keep the task's full
    # available points in the denominator, so the final score is computed over
    # a fixed total (the sum of every task's possible points) regardless of how
    # the failure was classified. infrastructure_error is included here on
    # purpose: the denominator must never shrink.
    if result.status in {"extraction_error", "build_failed", "infrastructure_error"}:
        return TaskScore(
            task_id=task.id,
            status=result.status,
            llm_response_time_seconds=result.llm_response_time_seconds,
            llm_usage=result.llm_usage,
            earned_points=0,
            available_points=available,
            compile_points=0,
            earned_test_points=0,
            passed_tests=result.passed_tests,
            failed_tests=result.failed_tests,
            generator=result.generator,
            opencode_metadata=result.opencode_metadata,
            temperature=result.temperature,
        )

    earned_test_points = sum(
        points
        for test_name, points in task.score.tests.items()
        if test_name in result.passed_tests
    )
    earned = task.score.compile + earned_test_points
    return TaskScore(
        task_id=task.id,
        status=result.status,
        llm_response_time_seconds=result.llm_response_time_seconds,
        llm_usage=result.llm_usage,
        earned_points=earned,
        available_points=available,
        compile_points=task.score.compile,
        earned_test_points=earned_test_points,
        passed_tests=result.passed_tests,
        failed_tests=result.failed_tests,
        generator=result.generator,
        opencode_metadata=result.opencode_metadata,
        temperature=result.temperature,
    )


def score_benchmark(task_scores: list[TaskScore]) -> BenchmarkScore:
    earned = sum(score.earned_points for score in task_scores)
    available = sum(score.available_points for score in task_scores)
    final_score = round((earned / available) * 100, 2) if available else 0.0
    return BenchmarkScore(
        earned_points=earned,
        available_points=available,
        final_score=final_score,
        task_scores=tuple(task_scores),
    )
