from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from benchmark.simple_yaml import load_yaml


@dataclass(frozen=True)
class LlmConfig:
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    model: str = "local-model-name"
    quantization: str = "unknown"
    temperature: float = 0.0
    seed: int = 42
    timeout_seconds: int = 120
    requests_per_minute: int | None = None


@dataclass(frozen=True)
class BenchmarkConfig:
    difficulty: str | None = None
    output_dir: Path = Path("results")
    max_attempts_per_task: int = 1
    task_id: str | None = None
    evaluation_workers: int = 1


@dataclass(frozen=True)
class DockerConfig:
    image: str = "csharp-llm-benchmark-dotnet10"
    timeout_seconds: int = 60
    memory_limit: str = "512m"
    cpus: str = "1.0"
    pids_limit: int = 200
    network: str = "none"
    read_only: bool = True
    cap_drop: tuple[str, ...] = ("ALL",)


@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig = field(default_factory=LlmConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)


def load_config(path: Path | None) -> AppConfig:
    data: dict[str, Any] = {}
    if path is not None:
        data = load_yaml(path)

    llm_data = data.get("llm", {})
    benchmark_data = data.get("benchmark", {})
    docker_data = data.get("docker", {})

    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or str(llm_data.get("api_key", LlmConfig.api_key))
    )

    return AppConfig(
        llm=LlmConfig(
            base_url=str(llm_data.get("base_url", LlmConfig.base_url)).rstrip("/"),
            api_key=api_key,
            model=str(llm_data.get("model", LlmConfig.model)),
            quantization=(
                _optional_string(llm_data.get("quantization"))
                or LlmConfig.quantization
            ),
            temperature=float(llm_data.get("temperature", LlmConfig.temperature)),
            seed=int(llm_data.get("seed", LlmConfig.seed)),
            timeout_seconds=int(
                llm_data.get("timeout_seconds", LlmConfig.timeout_seconds)
            ),
            requests_per_minute=_optional_positive_int(
                llm_data.get("requests_per_minute"),
                "llm.requests_per_minute",
            ),
        ),
        benchmark=BenchmarkConfig(
            difficulty=_optional_string(benchmark_data.get("difficulty")),
            output_dir=Path(
                str(benchmark_data.get("output_dir", BenchmarkConfig.output_dir))
            ),
            max_attempts_per_task=int(
                benchmark_data.get(
                    "max_attempts_per_task",
                    BenchmarkConfig.max_attempts_per_task,
                )
            ),
            task_id=_optional_string(benchmark_data.get("task_id")),
            evaluation_workers=_positive_int(
                benchmark_data.get(
                    "evaluation_workers",
                    BenchmarkConfig.evaluation_workers,
                ),
                "benchmark.evaluation_workers",
            ),
        ),
        docker=DockerConfig(
            image=str(docker_data.get("image", DockerConfig.image)),
            timeout_seconds=int(
                docker_data.get("timeout_seconds", DockerConfig.timeout_seconds)
            ),
            memory_limit=str(
                docker_data.get("memory_limit", DockerConfig.memory_limit)
            ),
            cpus=str(docker_data.get("cpus", DockerConfig.cpus)),
            pids_limit=int(docker_data.get("pids_limit", DockerConfig.pids_limit)),
            network=str(docker_data.get("network", DockerConfig.network)),
            read_only=bool(docker_data.get("read_only", DockerConfig.read_only)),
            cap_drop=tuple(docker_data.get("cap_drop", list(DockerConfig.cap_drop))),
        ),
    )


def apply_cli_overrides(
    config: AppConfig,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    difficulty: str | None = None,
    output_dir: str | None = None,
    task_id: str | None = None,
    evaluation_workers: int | None = None,
) -> AppConfig:
    return AppConfig(
        llm=LlmConfig(
            base_url=(base_url or config.llm.base_url).rstrip("/"),
            api_key=api_key or config.llm.api_key,
            model=model or config.llm.model,
            quantization=config.llm.quantization,
            temperature=config.llm.temperature,
            seed=config.llm.seed,
            timeout_seconds=config.llm.timeout_seconds,
            requests_per_minute=config.llm.requests_per_minute,
        ),
        benchmark=BenchmarkConfig(
            difficulty=(
                _optional_string(difficulty)
                if difficulty is not None
                else config.benchmark.difficulty
            ),
            output_dir=Path(output_dir) if output_dir else config.benchmark.output_dir,
            max_attempts_per_task=config.benchmark.max_attempts_per_task,
            task_id=task_id if task_id is not None else config.benchmark.task_id,
            evaluation_workers=(
                _positive_int(evaluation_workers, "benchmark.evaluation_workers")
                if evaluation_workers is not None
                else config.benchmark.evaluation_workers
            ),
        ),
        docker=config.docker,
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int(value: Any, name: str) -> int:
    number = int(value)
    if number < 1:
        raise ValueError(f"{name} must be at least 1")
    return number


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number == 0:
        return None
    if number < 0:
        raise ValueError(f"{name} must be at least 1 when set")
    return number
