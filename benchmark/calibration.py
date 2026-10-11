"""Unscored probes that select concurrency and calibrate session deadlines."""
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
class ConcurrencyTrial:
    generation_workers: int
    warmup_samples: tuple[ProbeMeasurement, ...]
    rounds: tuple[tuple[ProbeMeasurement, ...], ...]
    tokens_per_second: float


@dataclass(frozen=True)
class ConcurrencyCalibrationResult:
    max_generation_workers: int
    generation_workers: int
    tokens_per_second: float
    calibration_seconds: float
    trials: tuple[ConcurrencyTrial, ...]


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
    concurrency_calibration: ConcurrencyCalibrationResult | None = None


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


def calibrate_concurrency(config: AppConfig) -> ConcurrencyCalibrationResult | None:
    maximum = config.benchmark.generation_workers
    if maximum == 1:
        return None
    settings = config.benchmark.calibration
    trials = []
    started = time.perf_counter()
    print(f"Concurrency calibration: testing 2 through {maximum} concurrent requests", flush=True)
    for workers in range(2, maximum + 1):
        candidate = replace(config, benchmark=replace(config.benchmark, generation_workers=workers))
        print(f"Concurrency warmup: {workers} concurrent requests", flush=True)
        warmup = _round(candidate, settings.warmup_tokens)
        rounds = []
        for index in range(settings.rounds):
            print(
                f"Concurrency calibration: {workers} requests, round {index + 1}/{settings.rounds}",
                flush=True,
            )
            rounds.append(_round(candidate, settings.sample_tokens))
        # Compare the mean of the summed request rates across measured rounds.
        # Warmups are excluded and ties retain the smaller worker count.
        throughput = math.fsum(
            math.fsum(sample.tokens_per_second for sample in samples) for samples in rounds
        ) / len(rounds)
        comparison = f"; previous: {trials[-1].tokens_per_second:.2f}" if trials else ""
        print(f"Concurrency {workers}: {throughput:.2f} summed output tokens/s{comparison}", flush=True)
        trials.append(ConcurrencyTrial(workers, warmup, tuple(rounds), throughput))
    best = max(trials, key=lambda trial: trial.tokens_per_second)
    print(
        f"Selected generation_workers: {best.generation_workers}/{maximum} "
        f"({best.tokens_per_second:.2f} summed output tokens/s)",
        flush=True,
    )
    return ConcurrencyCalibrationResult(
        maximum, best.generation_workers, best.tokens_per_second,
        time.perf_counter() - started, tuple(trials),
    )


def calibrate(config: AppConfig) -> CalibrationResult:
    concurrency = (
        calibrate_concurrency(config) if config.benchmark.calibration.concurrency_enabled else None
    )
    if concurrency is not None:
        config = replace(config, benchmark=replace(
            config.benchmark, generation_workers=concurrency.generation_workers,
        ))
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
        warmup, tuple(samples), speed, timeout, concurrency,
    )


def apply_calibration(config: AppConfig, result: CalibrationResult) -> AppConfig:
    return replace(
        config,
        benchmark=replace(config.benchmark, generation_workers=result.generation_workers),
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
    concurrency = payload.get("concurrency_calibration")
    configured_workers = (
        concurrency["max_generation_workers"] if concurrency else payload.get("generation_workers")
    )
    if configured_workers != config.benchmark.generation_workers:
        raise ValueError("Saved calibration generation_workers differs from this configuration; start a new run")
    # This switch controls new probes only. Resume preserves the saved selection,
    # including runs created before the search became optional.
    saved_settings = payload.get("settings")
    expected_settings = asdict(config.benchmark.calibration)
    expected_settings.pop("concurrency_enabled")
    if not isinstance(saved_settings, dict) or {
        key: value for key, value in saved_settings.items() if key != "concurrency_enabled"
    } != expected_settings:
        raise ValueError("Saved calibration settings differs from this configuration; start a new run")
    for key, expected in (
        ("model", config.llm.model), ("base_url", config.llm.base_url),
        ("sampling", _sampling(config)),
    ):
        if payload.get(key) != expected:
            raise ValueError(f"Saved calibration {key} differs from this configuration; start a new run")
    payload["warmup_samples"] = tuple(ProbeMeasurement(**s) for s in payload["warmup_samples"])
    payload["samples"] = tuple(ProbeMeasurement(**s) for s in payload["samples"])
    if concurrency:
        concurrency["trials"] = tuple(
            ConcurrencyTrial(
                trial["generation_workers"],
                tuple(ProbeMeasurement(**s) for s in trial["warmup_samples"]),
                tuple(tuple(ProbeMeasurement(**s) for s in samples) for samples in trial["rounds"]),
                trial["tokens_per_second"],
            )
            for trial in concurrency["trials"]
        )
        payload["concurrency_calibration"] = ConcurrencyCalibrationResult(**concurrency)
    result = CalibrationResult(**payload)
    if result.concurrency_calibration is not None:
        concurrency_result = result.concurrency_calibration
        if (
            not concurrency_result.trials
            or concurrency_result.generation_workers != result.generation_workers
            or not 2 <= result.generation_workers <= concurrency_result.max_generation_workers
            or max(concurrency_result.trials, key=lambda trial: trial.tokens_per_second).generation_workers
            != result.generation_workers
        ):
            raise ValueError("Saved calibration concurrency selection is inconsistent")
    if result.timeout_seconds != calculate_timeout(result.tokens_per_second, config.benchmark.calibration):
        raise ValueError("Saved calibration timeout is inconsistent with its speed and settings")
    return result
