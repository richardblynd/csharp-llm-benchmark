from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from benchmark.simple_yaml import load_yaml


DEFAULT_TEMPERATURES = (0.2, 0.40, 0.60)
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 50
DEFAULT_REPETITION_PENALTY = 1.0


@dataclass(frozen=True)
class LlmConfig:
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    model: str = "local-model-name"
    model_label: str | None = None
    company: str | None = None
    quantization: str = "unknown"
    temperature: float = DEFAULT_TEMPERATURES[0]
    temperatures: tuple[float, ...] = DEFAULT_TEMPERATURES
    top_p: float = DEFAULT_TOP_P
    top_k: int = DEFAULT_TOP_K
    repetition_penalty: float = DEFAULT_REPETITION_PENALTY
    seed: int = 42
    timeout_seconds: int = 120
    requests_per_minute: int | None = None

    @property
    def effective_model_label(self) -> str:
        return self.model_label or self.model


@dataclass(frozen=True)
class BenchmarkConfig:
    difficulty: str | None = None
    output_dir: Path = Path("results")
    max_attempts_per_task: int = 1
    task_id: str | None = None
    evaluation_workers: int = 1
    generator: str = "llm"


@dataclass(frozen=True)
class DockerConfig:
    image: str = "csharp-llm-benchmark-dotnet8"
    timeout_seconds: int = 60
    memory_limit: str = "512m"
    cpus: str = "1.0"
    pids_limit: int = 200
    network: str = "none"
    read_only: bool = True
    cap_drop: tuple[str, ...] = ("ALL",)


@dataclass(frozen=True)
class OpenCodeConfig:
    version: str | None = None
    package: str = "opencode-ai"
    docker_image: str = "csharp-llm-benchmark-opencode"
    cache_dir: Path = Path(".cache/opencode")
    timeout_seconds: int = 900
    keep_timed_out_containers: bool = False
    max_steps: int = 40
    network: str = "bridge"
    container_base_url: str | None = None
    context_limit: int | None = None
    output_limit: int | None = None
    compaction_auto: bool = True
    compaction_prune: bool = True
    compaction_reserved: int | None = 10000


@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig = field(default_factory=LlmConfig)
    benchmark: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)


def load_config(path: Path | None) -> AppConfig:
    data: dict[str, Any] = {}
    if path is not None:
        data = load_yaml(path)

    llm_data = data.get("llm", {})
    benchmark_data = data.get("benchmark", {})
    docker_data = data.get("docker", {})
    opencode_data = data.get("opencode", {})
    opencode_compaction_data = opencode_data.get("compaction", {})
    if not isinstance(opencode_compaction_data, dict):
        raise ValueError("opencode.compaction must be a mapping when set")

    api_key = (
        os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or str(llm_data.get("api_key", LlmConfig.api_key))
    )

    model = str(llm_data.get("model", LlmConfig.model))
    model_label = _optional_string(
        llm_data.get("modelLabel", llm_data.get("model_label"))
    )
    company = _optional_string(llm_data.get("company"))
    temperatures = _temperature_tuple(llm_data)

    config = AppConfig(
        llm=LlmConfig(
            base_url=str(llm_data.get("base_url", LlmConfig.base_url)).rstrip("/"),
            api_key=api_key,
            model=model,
            model_label=model_label,
            company=company,
            quantization=(
                _optional_string(llm_data.get("quantization"))
                or LlmConfig.quantization
            ),
            temperature=temperatures[0],
            temperatures=temperatures,
            top_p=_positive_float(
                llm_data.get("top_p", LlmConfig.top_p),
                "llm.top_p",
            ),
            top_k=_positive_int(llm_data.get("top_k", LlmConfig.top_k), "llm.top_k"),
            repetition_penalty=_positive_float(
                llm_data.get(
                    "repetition_penalty",
                    LlmConfig.repetition_penalty,
                ),
                "llm.repetition_penalty",
            ),
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
            generator=_generator_value(
                benchmark_data.get("generator", BenchmarkConfig.generator),
                "benchmark.generator",
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
        opencode=OpenCodeConfig(
            version=_optional_string(opencode_data.get("version")),
            package=str(opencode_data.get("package", OpenCodeConfig.package)),
            docker_image=str(
                opencode_data.get("docker_image", OpenCodeConfig.docker_image)
            ),
            cache_dir=Path(
                str(opencode_data.get("cache_dir", OpenCodeConfig.cache_dir))
            ),
            timeout_seconds=_positive_int(
                opencode_data.get(
                    "timeout_seconds",
                    OpenCodeConfig.timeout_seconds,
                ),
                "opencode.timeout_seconds",
            ),
            keep_timed_out_containers=_bool_value(
                opencode_data.get(
                    "keep_timed_out_containers",
                    OpenCodeConfig.keep_timed_out_containers,
                ),
                "opencode.keep_timed_out_containers",
            ),
            max_steps=_positive_int(
                opencode_data.get("max_steps", OpenCodeConfig.max_steps),
                "opencode.max_steps",
            ),
            network=str(opencode_data.get("network", OpenCodeConfig.network)),
            container_base_url=_optional_string(
                opencode_data.get("container_base_url")
            ),
            context_limit=_optional_positive_int(
                opencode_data.get("context_limit"),
                "opencode.context_limit",
            ),
            output_limit=_optional_positive_int(
                opencode_data.get("output_limit"),
                "opencode.output_limit",
            ),
            compaction_auto=_bool_value(
                opencode_compaction_data.get(
                    "auto",
                    OpenCodeConfig.compaction_auto,
                ),
                "opencode.compaction.auto",
            ),
            compaction_prune=_bool_value(
                opencode_compaction_data.get(
                    "prune",
                    OpenCodeConfig.compaction_prune,
                ),
                "opencode.compaction.prune",
            ),
            compaction_reserved=_optional_positive_int(
                opencode_compaction_data.get(
                    "reserved",
                    OpenCodeConfig.compaction_reserved,
                ),
                "opencode.compaction.reserved",
            ),
        ),
    )
    _validate_config(config)
    return config


def apply_cli_overrides(
    config: AppConfig,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    model_label: str | None = None,
    company: str | None = None,
    difficulty: str | None = None,
    output_dir: str | None = None,
    task_id: str | None = None,
    evaluation_workers: int | None = None,
    generator: str | None = None,
    opencode_version: str | None = None,
    opencode_timeout_seconds: int | None = None,
) -> AppConfig:
    updated = AppConfig(
        llm=LlmConfig(
            base_url=(base_url or config.llm.base_url).rstrip("/"),
            api_key=api_key or config.llm.api_key,
            model=model or config.llm.model,
            model_label=(
                _optional_string(model_label)
                if model_label is not None
                else config.llm.model_label
            ),
            company=(
                _optional_string(company)
                if company is not None
                else config.llm.company
            ),
            quantization=config.llm.quantization,
            temperature=config.llm.temperature,
            temperatures=config.llm.temperatures,
            top_p=config.llm.top_p,
            top_k=config.llm.top_k,
            repetition_penalty=config.llm.repetition_penalty,
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
            generator=(
                _generator_value(generator, "benchmark.generator")
                if generator is not None
                else config.benchmark.generator
            ),
        ),
        docker=config.docker,
        opencode=OpenCodeConfig(
            version=(
                _optional_string(opencode_version)
                if opencode_version is not None
                else config.opencode.version
            ),
            package=config.opencode.package,
            docker_image=config.opencode.docker_image,
            cache_dir=config.opencode.cache_dir,
            timeout_seconds=(
                _positive_int(
                    opencode_timeout_seconds,
                    "opencode.timeout_seconds",
                )
                if opencode_timeout_seconds is not None
                else config.opencode.timeout_seconds
            ),
            keep_timed_out_containers=config.opencode.keep_timed_out_containers,
            max_steps=config.opencode.max_steps,
            network=config.opencode.network,
            container_base_url=config.opencode.container_base_url,
            context_limit=config.opencode.context_limit,
            output_limit=config.opencode.output_limit,
            compaction_auto=config.opencode.compaction_auto,
            compaction_prune=config.opencode.compaction_prune,
            compaction_reserved=config.opencode.compaction_reserved,
        ),
    )
    _validate_config(updated)
    return updated


def with_llm_temperature(config: AppConfig, temperature: float) -> AppConfig:
    return replace(config, llm=replace(config.llm, temperature=temperature))


def _temperature_tuple(llm_data: dict[str, Any]) -> tuple[float, ...]:
    temperatures_value = llm_data.get("temperatures")
    if temperatures_value is not None:
        if not isinstance(temperatures_value, list):
            raise ValueError("llm.temperatures must be a list of numbers")
        temperatures = tuple(float(value) for value in temperatures_value)
    elif "temperature" in llm_data:
        temperatures = (float(llm_data["temperature"]),)
    else:
        temperatures = LlmConfig.temperatures

    if not temperatures:
        raise ValueError("llm.temperatures must contain at least one temperature")
    return temperatures


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


def _positive_float(value: Any, name: str) -> float:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return number


def _generator_value(value: Any, name: str) -> str:
    text = str(value).strip().lower()
    if text not in {"llm", "opencode"}:
        raise ValueError(f"{name} must be 'llm' or 'opencode'")
    return text


def _validate_config(config: AppConfig) -> None:
    if config.benchmark.generator == "opencode" and not config.opencode.version:
        raise ValueError(
            "opencode.version is required when benchmark.generator is 'opencode'"
        )


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number == 0:
        return None
    if number < 0:
        raise ValueError(f"{name} must be at least 1 when set")
    return number


def _bool_value(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "on", "1"}:
        return True
    if text in {"false", "no", "off", "0"}:
        return False
    raise ValueError(f"{name} must be a boolean")
