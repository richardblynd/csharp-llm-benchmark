"""Unscored inference probes that calibrate agent session deadlines under load."""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark.config import AppConfig, CalibrationConfig


@dataclass(frozen=True)
class ProbeMeasurement:
    output_tokens: int
    elapsed_seconds: float
    time_to_first_token_seconds: float | None
    tokens_per_second: float


@dataclass(frozen=True)
class CalibrationResult:
    measured_at: str
    model: str
    base_url: str
    generation_workers: int
    settings: dict[str, Any]
    sampling: dict[str, Any]
    warmup_seconds: float
    calibration_seconds: float
    warmup_samples: tuple[ProbeMeasurement, ...]
    samples: tuple[ProbeMeasurement, ...]
    tokens_per_second: float
    timeout_seconds: int


def _sampling(config: AppConfig) -> dict[str, Any]:
    return {
        key: getattr(config.llm, key)
        for key in ("temperature", "top_p", "min_p", "top_k", "repetition_penalty")
        if getattr(config.llm, key) is not None
    }


def calculate_timeout(speed: float, settings: CalibrationConfig) -> int:
    if not math.isfinite(speed) or speed <= 0:
        raise ValueError("Calibration speed must be finite and positive")
    return max(
        settings.min_timeout_seconds,
        math.ceil(settings.safety_factor * (settings.token_budget / speed + settings.overhead_seconds)),
    )


def _probe(config: AppConfig, max_tokens: int, barrier: threading.Barrier) -> ProbeMeasurement:
    payload = {
        "model": config.llm.model,
        **_sampling(config),
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [
            {"role": "system", "content": "You write C# code. Output code directly."},
            {"role": "user", "content": (
                f"Calibration request {uuid.uuid4().hex}. "
                "Write a large C# class with 200 numbered methods. Each method validates "
                "its integer input and calculates a different arithmetic result. "
                "Write every method in full, without abbreviations or explanations."
            )},
        ],
    }
    request = urllib.request.Request(
        config.llm.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.llm.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    barrier.wait()
    started = time.perf_counter()
    first_token = None
    output_tokens = None
    completed = False
    timeout = config.benchmark.calibration.request_timeout_seconds
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                if time.perf_counter() - started > timeout:
                    raise TimeoutError("Calibration request exceeded its time limit")
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    completed = True
                    break
                event = json.loads(data)
                if event.get("error"):
                    raise RuntimeError("Calibration endpoint reported a generation error")
                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    if first_token is None and any(
                        delta.get(key) for key in ("content", "reasoning", "reasoning_content")
                    ):
                        first_token = time.perf_counter() - started
                usage = event.get("usage")
                if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                    output_tokens = usage["completion_tokens"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Speed calibration request failed with HTTP {exc.code}. Check the provider's "
            "server logs, or disable calibration explicitly with --calibration-enabled false."
        ) from exc
    except (OSError, urllib.error.URLError, ValueError) as exc:
        # Do not include request headers or provider error bodies in diagnostics.
        raise RuntimeError(
            "Speed calibration request failed. Check the endpoint and streaming support, "
            "increase benchmark.calibration.request_timeout_seconds, or disable calibration "
            "explicitly with --calibration-enabled false."
        ) from exc
    elapsed = time.perf_counter() - started
    if not completed or isinstance(output_tokens, bool) or not isinstance(output_tokens, int) or output_tokens <= 0:
        raise RuntimeError(
            "Speed calibration requires a completed stream with positive usage.completion_tokens. "
            "The provider must support stream_options.include_usage."
        )
    return ProbeMeasurement(output_tokens, elapsed, first_token, output_tokens / elapsed)


def _round(config: AppConfig, tokens: int) -> tuple[ProbeMeasurement, ...]:
    workers = config.benchmark.generation_workers
    barrier = threading.Barrier(workers)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="benchmark-calibration") as executor:
        futures = [executor.submit(_probe, config, tokens, barrier) for _ in range(workers)]
        return tuple(future.result() for future in futures)


def calibrate(config: AppConfig) -> CalibrationResult:
    settings = config.benchmark.calibration
    workers = config.benchmark.generation_workers
    print(f"Warmup: {workers} concurrent requests, up to {settings.warmup_tokens} output tokens each", flush=True)
    started = time.perf_counter()
    warmup = _round(config, settings.warmup_tokens)
    warmup_seconds = time.perf_counter() - started
    samples = []
    started = time.perf_counter()
    for index in range(settings.rounds):
        print(f"Speed calibration: round {index + 1}/{settings.rounds}, {workers} concurrent requests", flush=True)
        samples.extend(_round(config, settings.sample_tokens))
    calibration_seconds = time.perf_counter() - started
    speed = min(sample.tokens_per_second for sample in samples)
    timeout = calculate_timeout(speed, settings)
    print(f"Calibrated speed: {speed:.2f} output tokens/s per request; agent timeout: {timeout}s", flush=True)
    return CalibrationResult(
        datetime.now(timezone.utc).isoformat(), config.llm.model, config.llm.base_url,
        workers, asdict(settings), _sampling(config), warmup_seconds, calibration_seconds,
        warmup, tuple(samples), speed, timeout,
    )


def apply_calibration(config: AppConfig, result: CalibrationResult) -> AppConfig:
    return replace(
        config,
        pi=replace(config.pi, timeout_seconds=result.timeout_seconds),
        opencode=replace(config.opencode, timeout_seconds=result.timeout_seconds),
    )


def save_calibration(run_dir: Path, result: CalibrationResult) -> None:
    path = run_dir / "calibration.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_calibration(run_dir: Path, config: AppConfig) -> CalibrationResult:
    path = run_dir / "calibration.json"
    if not path.exists():
        raise ValueError(
            "This run has no saved speed calibration. Start a new run, or resume the "
            "existing methodology with --calibration-enabled false."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in (
        ("model", config.llm.model), ("base_url", config.llm.base_url),
        ("generation_workers", config.benchmark.generation_workers),
        ("settings", asdict(config.benchmark.calibration)), ("sampling", _sampling(config)),
    ):
        if payload.get(key) != expected:
            raise ValueError(f"Saved calibration {key} differs from this configuration; start a new run")
    payload["warmup_samples"] = tuple(ProbeMeasurement(**s) for s in payload["warmup_samples"])
    payload["samples"] = tuple(ProbeMeasurement(**s) for s in payload["samples"])
    result = CalibrationResult(**payload)
    if result.timeout_seconds != calculate_timeout(result.tokens_per_second, config.benchmark.calibration):
        raise ValueError("Saved calibration timeout is inconsistent with its speed and settings")
    return result
