from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol
from urllib.parse import urlsplit, urlunsplit

from benchmark.config import AppConfig, OpenCodeConfig
from benchmark.llm_client import (
    ExtractedCode,
    LlmClient,
    LlmHttpError,
    SYSTEM_PROMPT,
    LlmTimeoutError,
    LlmUsage,
    RequestRateLimiter,
    extract_solution_code,
)
from benchmark.runner import CommandResult
from benchmark.tasks import Task


@dataclass(frozen=True)
class OpenCodeRunMetadata:
    version_configured: str
    version_resolved: str | None
    package: str
    install_time_seconds: float
    session_time_seconds: float
    exit_code: int
    timed_out: bool = False
    container_name: str | None = None
    attempts: int = 1


@dataclass(frozen=True)
class OpenCodePreflight:
    version_configured: str
    version_resolved: str | None
    package: str
    install_time_seconds: float
    install_output: str


@dataclass(frozen=True)
class PreparedOpenCodeGeneration:
    task: Task
    task_dir: Path
    workspace: Path
    preflight: OpenCodePreflight
    container_name: str
    docker_command: list[str]
    precreated: bool = False


@dataclass(frozen=True)
class GeneratedSolution:
    extracted: ExtractedCode
    llm_response_time_seconds: float
    llm_usage: LlmUsage
    generator: str = "llm"
    opencode_metadata: OpenCodeRunMetadata | None = None
    infrastructure_error: str | None = None


class SolutionGenerator(Protocol):
    def generate(self, task: Task, task_dir: Path) -> GeneratedSolution:
        ...


class DirectLlmGenerator:
    def __init__(self, config: AppConfig):
        self._client = LlmClient(config.llm)

    def generate(self, task: Task, task_dir: Path) -> GeneratedSolution:
        prompt = task.prompt
        (task_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        try:
            llm_response = self._client.complete(prompt)
        except LlmTimeoutError as exc:
            (task_dir / "generation-error.log").write_text(
                str(exc) + "\n", encoding="utf-8"
            )
            return GeneratedSolution(
                extracted=ExtractedCode(code=None, warnings=(), error=str(exc)),
                llm_response_time_seconds=exc.response_time_seconds,
                llm_usage=LlmUsage(),
                generator="llm",
            )
        except LlmHttpError as exc:
            if exc.status_code != 400:
                raise
            (task_dir / "generation-error.log").write_text(
                f"LLM HTTP error {exc.status_code}: {exc.details}\n",
                encoding="utf-8",
            )
            return GeneratedSolution(
                extracted=ExtractedCode(
                    code=None,
                    warnings=(),
                    error=(
                        f"LLM HTTP error {exc.status_code} during generation. "
                        "See generation-error.log."
                    ),
                ),
                llm_response_time_seconds=exc.response_time_seconds,
                llm_usage=LlmUsage(),
                generator="llm",
            )

        (task_dir / "response.md").write_text(llm_response.content, encoding="utf-8")
        required_public_class = task.solution_class if task.difficulty == "easy" else None
        extracted = extract_solution_code(
            llm_response.content,
            required_public_class=required_public_class,
        )
        if extracted.code is not None:
            generated_path = task_dir / task.generated_file
            generated_path.parent.mkdir(parents=True, exist_ok=True)
            generated_path.write_text(extracted.code, encoding="utf-8")

        return GeneratedSolution(
            extracted=extracted,
            llm_response_time_seconds=llm_response.response_time_seconds,
            llm_usage=llm_response.usage,
            generator="llm",
        )


class OpenCodeGenerator:
    _preflight_lock: ClassVar[threading.Lock] = threading.Lock()
    _preflight_cache: ClassVar[dict[tuple[str, ...], OpenCodePreflight]] = {}

    def __init__(self, config: AppConfig):
        if config.opencode.version is None:
            raise ValueError("opencode.version is required for the opencode generator")
        self._llm = config.llm
        self._opencode = config.opencode
        self._rate_limiter = RequestRateLimiter(config.llm.requests_per_minute)

    def generate(self, task: Task, task_dir: Path) -> GeneratedSolution:
        return self.run_prepared(self.prepare(task, task_dir))

    def preflight(self) -> OpenCodePreflight:
        cache_key = self._preflight_cache_key()
        with self._preflight_lock:
            cached = self._preflight_cache.get(cache_key)
            if cached is not None:
                return cached

            install_started_at = time.perf_counter()
            install = self._ensure_opencode_installed()
            install_time_seconds = time.perf_counter() - install_started_at
            version_resolved = _last_non_empty_line(install.stdout)
            if install.exit_code != 0:
                raise RuntimeError(
                    "OpenCode installation failed: " + install.combined_output
                )

            preflight = OpenCodePreflight(
                version_configured=self._opencode.version,
                version_resolved=version_resolved,
                package=self._opencode.package,
                install_time_seconds=install_time_seconds,
                install_output=install.combined_output,
            )
            self._preflight_cache[cache_key] = preflight
            return preflight

    def prepare(self, task: Task, task_dir: Path) -> PreparedOpenCodeGeneration:
        preflight = self.preflight()
        prompt = self._build_agent_prompt(task)
        (task_dir / "prompt.md").write_text(task.prompt, encoding="utf-8")
        (task_dir / "opencode-prompt.md").write_text(prompt, encoding="utf-8")
        (task_dir / "opencode-install.log").write_text(
            preflight.install_output + "\n",
            encoding="utf-8",
        )

        workspace = self._prepare_workspace(task, task_dir, prompt)
        self._write_opencode_config(workspace)
        home_dir = task_dir / "opencode-home"
        home_dir.mkdir(parents=True, exist_ok=True)
        container_name = _container_name("task", task.id, include_prefix=False)
        docker_command = self._opencode_docker_command(
            task,
            workspace,
            home_dir,
            container_name=container_name,
            create=self._opencode.precreate_container,
        )
        if self._opencode.precreate_container:
            create = self._run_docker(
                docker_command,
                timeout=30,
                env={"OPENCODE_BENCHMARK_API_KEY": self._llm.api_key},
            )
            if create.exit_code != 0:
                self._remove_container(container_name)
                raise RuntimeError(
                    "OpenCode container preparation failed: "
                    + create.combined_output
                )
        return PreparedOpenCodeGeneration(
            task=task,
            task_dir=task_dir,
            workspace=workspace,
            preflight=preflight,
            container_name=container_name,
            docker_command=docker_command,
            precreated=self._opencode.precreate_container,
        )

    def run_prepared(
        self,
        prepared: PreparedOpenCodeGeneration,
    ) -> GeneratedSolution:
        self._rate_limiter.wait()
        max_attempts = 1 + max(0, self._opencode.session_retries)
        attempt = 0
        run: CommandResult | None = None
        retry_log: list[str] = []
        try:
            while True:
                attempt += 1
                run, session_time_seconds = self._execute_session(prepared, attempt)
                self._write_session_logs(prepared, run)
                solution, transient = self._build_solution(
                    prepared,
                    run,
                    session_time_seconds,
                    attempt,
                )
                if not transient or attempt >= max_attempts:
                    if retry_log:
                        retry_log.append(
                            f"Attempt {attempt} succeeded or exhausted retries "
                            f"(status: "
                            f"{'infrastructure_error' if solution.infrastructure_error else 'usable result'})."
                        )
                        (prepared.task_dir / "opencode-retries.log").write_text(
                            "\n".join(retry_log) + "\n",
                            encoding="utf-8",
                        )
                    return solution
                retry_log.append(
                    f"Attempt {attempt} produced no usable model result "
                    f"(exit_code={run.exit_code}, "
                    f"session_time={session_time_seconds:.2f}s, "
                    f"events_bytes={len(run.stdout)}); retrying."
                )
        finally:
            preserve_timeout_home = (
                run is not None
                and run.timed_out
                and self._opencode.keep_timed_out_containers
            )
            self._cleanup_opencode_home(prepared, preserve=preserve_timeout_home)

    def _execute_session(
        self,
        prepared: PreparedOpenCodeGeneration,
        attempt: int,
    ) -> tuple[CommandResult, float]:
        session_started_at = time.perf_counter()
        if attempt == 1 and prepared.precreated:
            run = self._start_precreated_opencode(prepared)
        elif attempt == 1:
            run = self._run_docker(
                prepared.docker_command,
                timeout=self._opencode.timeout_seconds,
                env={"OPENCODE_BENCHMARK_API_KEY": self._llm.api_key},
                keep_on_timeout=self._opencode.keep_timed_out_containers,
            )
        else:
            run = self._run_fresh_session(prepared)
        return run, time.perf_counter() - session_started_at

    def _run_fresh_session(
        self,
        prepared: PreparedOpenCodeGeneration,
    ) -> CommandResult:
        home_dir = prepared.task_dir / "opencode-home"
        home_dir.mkdir(parents=True, exist_ok=True)
        container_name = _container_name(
            "task", prepared.task.id, include_prefix=False
        )
        docker_command = self._opencode_docker_command(
            prepared.task,
            prepared.workspace,
            home_dir,
            container_name=container_name,
            create=False,
        )
        return self._run_docker(
            docker_command,
            timeout=self._opencode.timeout_seconds,
            env={"OPENCODE_BENCHMARK_API_KEY": self._llm.api_key},
            keep_on_timeout=self._opencode.keep_timed_out_containers,
        )

    def _write_session_logs(
        self,
        prepared: PreparedOpenCodeGeneration,
        run: CommandResult,
    ) -> None:
        task_dir = prepared.task_dir
        (task_dir / "response.md").write_text(run.stdout, encoding="utf-8")
        (task_dir / "opencode-events.jsonl").write_text(
            run.stdout,
            encoding="utf-8",
        )
        (task_dir / "opencode-stderr.log").write_text(
            run.stderr,
            encoding="utf-8",
        )

    def _build_solution(
        self,
        prepared: PreparedOpenCodeGeneration,
        run: CommandResult,
        session_time_seconds: float,
        attempts: int,
    ) -> tuple[GeneratedSolution, bool]:
        """Interpret a finished OpenCode session.

        Returns the generated solution and a flag indicating whether the
        failure is a transient empty session that is safe to retry.
        """
        task = prepared.task
        task_dir = prepared.task_dir
        workspace = prepared.workspace
        generated_path = workspace / task.generated_file
        metadata = OpenCodeRunMetadata(
            version_configured=prepared.preflight.version_configured,
            version_resolved=prepared.preflight.version_resolved,
            package=prepared.preflight.package,
            install_time_seconds=prepared.preflight.install_time_seconds,
            session_time_seconds=session_time_seconds,
            exit_code=run.exit_code,
            timed_out=run.timed_out,
            container_name=run.container_name,
            attempts=attempts,
        )
        usage = _parse_opencode_usage(run.stdout)
        opencode_error = _parse_opencode_error(run.stdout)
        if opencode_error is not None:
            return (
                GeneratedSolution(
                    extracted=ExtractedCode(
                        code=None,
                        warnings=(),
                        error=f"OpenCode reported an error: {opencode_error}",
                    ),
                    llm_response_time_seconds=session_time_seconds,
                    llm_usage=usage,
                    generator="opencode",
                    opencode_metadata=metadata,
                ),
                False,
            )

        if not generated_path.exists():
            if _opencode_session_missing_model_result(run.stdout):
                # An empty session (clean exit, no model output, no generated
                # file) is almost always a transient backend hiccup, not a
                # model failure: the same task succeeds on other attempts.
                # Signal that a retry is safe instead of recording a terminal
                # infrastructure error on the first empty session.
                transient = not run.timed_out
                return (
                    GeneratedSolution(
                        extracted=ExtractedCode(
                            code=None,
                            warnings=(),
                            error=None,
                        ),
                        llm_response_time_seconds=session_time_seconds,
                        llm_usage=usage,
                        generator="opencode",
                        opencode_metadata=metadata,
                        infrastructure_error=(
                            "OpenCode exited successfully but produced no model "
                            "result before creating the expected generated file "
                            f"{task.generated_file}"
                            + (
                                f" after {attempts} attempt(s)."
                                if attempts > 1
                                else "."
                            )
                        ),
                    ),
                    transient,
                )
            return (
                GeneratedSolution(
                    extracted=ExtractedCode(
                        code=None,
                        warnings=(),
                        error=(
                            "OpenCode did not create the expected generated file "
                            f"{task.generated_file}."
                        ),
                    ),
                    llm_response_time_seconds=session_time_seconds,
                    llm_usage=usage,
                    generator="opencode",
                    opencode_metadata=metadata,
                ),
                False,
            )

        code = generated_path.read_text(encoding="utf-8")
        required_public_class = (
            task.solution_class if task.difficulty == "easy" else None
        )
        extracted = extract_solution_code(
            code,
            required_public_class=required_public_class,
            preserve_unfenced_code=True,
        )
        warnings = list(extracted.warnings)
        if run.exit_code != 0:
            warnings.append(f"OpenCode exited with code {run.exit_code}.")
        extracted = ExtractedCode(
            code=extracted.code,
            warnings=tuple(warnings),
            error=extracted.error,
        )
        if extracted.code is not None:
            result_generated_path = task_dir / task.generated_file
            result_generated_path.parent.mkdir(parents=True, exist_ok=True)
            result_generated_path.write_text(extracted.code, encoding="utf-8")

        return (
            GeneratedSolution(
                extracted=extracted,
                llm_response_time_seconds=session_time_seconds,
                llm_usage=usage,
                generator="opencode",
                opencode_metadata=metadata,
            ),
            False,
        )

    def _ensure_opencode_installed(self) -> CommandResult:
        install_dir = self._opencode_install_dir()
        install_dir.mkdir(parents=True, exist_ok=True)
        package_spec = f"{self._opencode.package}@{self._opencode.version}"
        script = "\n".join(
            [
                "set -eu",
                "cd /opencode-install",
                f"expected={shlex.quote(package_spec)}",
                'actual="$(cat .opencode-package 2>/dev/null || true)"',
                'if [ "$actual" != "$expected" ]; then',
                "  rm -rf node_modules package.json package-lock.json .opencode-package",
                "  npm init -y >/dev/null",
                f"  npm install --no-audit --no-fund --silent {shlex.quote(package_spec)}",
                '  printf "%s\\n" "$expected" > .opencode-package',
                "fi",
                "node_modules/.bin/opencode --version",
            ]
        )
        return self._run_docker(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                _container_name("install", self._opencode.version or "unknown"),
                "--network",
                self._opencode.network,
                "--user",
                "root",
                "--mount",
                f"type=bind,source={install_dir.resolve()},target=/opencode-install",
                self._opencode.docker_image,
                "/bin/sh",
                "-lc",
                script,
            ],
            timeout=self._opencode.timeout_seconds,
            keep_on_timeout=False,
        )

    def cleanup_prepared(self, prepared: PreparedOpenCodeGeneration) -> None:
        if prepared.precreated:
            self._remove_container(prepared.container_name)
        self._cleanup_opencode_home(prepared)

    def _cleanup_opencode_home(
        self,
        prepared: PreparedOpenCodeGeneration,
        *,
        preserve: bool = False,
    ) -> None:
        if preserve:
            return
        home_dir = prepared.task_dir / "opencode-home"
        if home_dir.exists():
            shutil.rmtree(home_dir, ignore_errors=True)

    def _build_agent_prompt(self, task: Task) -> str:
        return _agent_prompt(task, self._opencode)

    def _prepare_workspace(self, task: Task, task_dir: Path, prompt: str) -> Path:
        workspace = task_dir / "opencode-workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        for public_file in task.public_files:
            if _is_generated_file(task, public_file):
                continue
            source = task.template_dir / public_file
            destination = workspace / public_file
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        (workspace / "BENCHMARK_PROMPT.md").write_text(prompt, encoding="utf-8")
        return workspace

    def _write_opencode_config(self, workspace: Path) -> None:
        model = self._llm.model
        opencode_model = f"benchmark/{model}"
        payload = {
            "$schema": "https://opencode.ai/config.json",
            "share": "disabled",
            "autoupdate": False,
            "permission": {
                "*": "allow",
                "question": "deny",
                "doom_loop": "deny",
                "task": "deny",
            },
            "compaction": self._compaction_config(),
            "model": opencode_model,
            "small_model": opencode_model,
            "provider": {
                "benchmark": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Benchmark OpenAI-compatible API",
                    "options": {
                        "baseURL": self._container_base_url(),
                        "apiKey": "{env:OPENCODE_BENCHMARK_API_KEY}",
                    },
                    "models": {
                        model: self._model_config(model),
                    },
                },
            },
        }
        (workspace / "opencode.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _compaction_config(self) -> dict[str, int | bool]:
        config: dict[str, int | bool] = {
            "auto": self._opencode.compaction_auto,
            "prune": self._opencode.compaction_prune,
        }
        if self._opencode.compaction_reserved is not None:
            config["reserved"] = self._opencode.compaction_reserved
        return config

    def _model_config(self, model: str) -> dict[str, Any]:
        options: dict[str, int | float] = {
            "temperature": self._llm.temperature,
        }
        if self._llm.top_p is not None:
            options["top_p"] = self._llm.top_p
        if self._llm.min_p is not None:
            options["min_p"] = self._llm.min_p
        if self._llm.top_k is not None:
            options["top_k"] = self._llm.top_k
        if self._llm.repetition_penalty is not None:
            options["repetition_penalty"] = self._llm.repetition_penalty
        config: dict[str, Any] = {
            "name": model,
            "options": options,
        }
        limit: dict[str, int] = {}
        if self._opencode.context_limit is not None:
            limit["context"] = self._opencode.context_limit
        if self._opencode.output_limit is not None:
            limit["output"] = self._opencode.output_limit
        if limit:
            config["limit"] = limit
        return config

    def _run_opencode(
        self,
        task: Task,
        task_dir: Path,
        workspace: Path,
    ) -> CommandResult:
        home_dir = task_dir / "opencode-home"
        home_dir.mkdir(parents=True, exist_ok=True)
        container_name = _container_name("task", task.id, include_prefix=False)
        docker_command = self._opencode_docker_command(
            task,
            workspace,
            home_dir,
            container_name=container_name,
            create=False,
        )
        return self._run_docker(
            docker_command,
            timeout=self._opencode.timeout_seconds,
            env={"OPENCODE_BENCHMARK_API_KEY": self._llm.api_key},
            keep_on_timeout=self._opencode.keep_timed_out_containers,
        )

    def _opencode_docker_command(
        self,
        task: Task,
        workspace: Path,
        home_dir: Path,
        *,
        container_name: str,
        create: bool,
    ) -> list[str]:
        install_dir = self._opencode_install_dir()
        env = [
            "--env",
            "OPENCODE_BENCHMARK_API_KEY",
            "--env",
            "OPENCODE_DISABLE_AUTOUPDATE=true",
            "--env",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS=true",
            "--env",
            "OPENCODE_DISABLE_CLAUDE_CODE=true",
            "--env",
            "OPENCODE_DISABLE_LSP_DOWNLOAD=true",
            "--env",
            "OPENCODE_CONFIG=/workspace/opencode.json",
            "--env",
            "HOME=/home/benchmark",
            "--env",
            "XDG_CONFIG_HOME=/home/benchmark/.config",
            "--env",
            "XDG_DATA_HOME=/home/benchmark/.local/share",
            "--env",
            "XDG_CACHE_HOME=/home/benchmark/.cache",
        ]
        script = "\n".join(
            [
                "set -eu",
                "cd /workspace",
                'prompt="$(cat /workspace/BENCHMARK_PROMPT.md)"',
                "/opencode-install/node_modules/.bin/opencode run "
                "--dir /workspace "
                f"--model {shlex.quote('benchmark/' + self._llm.model)} "
                "--format json "
                "--dangerously-skip-permissions "
                f"--title {shlex.quote(task.id)} "
                '"$prompt"',
            ]
        )
        docker_command = [
            "docker",
            "create" if create else "run",
        ]
        if not create:
            docker_command.append("--rm")
        docker_command.extend(
            [
                "--name",
                container_name,
                "--network",
                self._opencode.network,
                "--user",
                "root",
                "--add-host",
                "host.docker.internal:host-gateway",
                "--mount",
                f"type=bind,source={install_dir.resolve()},target=/opencode-install",
                "--mount",
                f"type=bind,source={workspace.resolve()},target=/workspace",
                "--mount",
                f"type=bind,source={home_dir.resolve()},target=/home/benchmark",
                *env,
                self._opencode.docker_image,
                "/bin/sh",
                "-lc",
                script,
            ]
        )
        return docker_command

    def _start_precreated_opencode(
        self,
        prepared: PreparedOpenCodeGeneration,
    ) -> CommandResult:
        timed_out = False
        try:
            run = self._run_docker(
                ["docker", "start", "--attach", prepared.container_name],
                timeout=self._opencode.timeout_seconds,
                env={"OPENCODE_BENCHMARK_API_KEY": self._llm.api_key},
                keep_on_timeout=self._opencode.keep_timed_out_containers,
            )
            timed_out = run.timed_out
            if run.timed_out and self._opencode.keep_timed_out_containers:
                return CommandResult(
                    exit_code=run.exit_code,
                    stdout=run.stdout,
                    stderr=run.stderr,
                    timed_out=run.timed_out,
                    container_name=prepared.container_name,
                )
            return CommandResult(
                exit_code=run.exit_code,
                stdout=run.stdout,
                stderr=run.stderr,
                timed_out=run.timed_out,
                container_name=prepared.container_name,
            )
        finally:
            if not (timed_out and self._opencode.keep_timed_out_containers):
                self._remove_container(prepared.container_name)

    def _remove_container(self, container_name: str) -> None:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _opencode_install_dir(self) -> Path:
        package_key = _safe_cache_key(self._opencode.package)
        version_key = _safe_cache_key(self._opencode.version or "unknown")
        return self._opencode.cache_dir / package_key / version_key

    def _preflight_cache_key(self) -> tuple[str, ...]:
        return (
            self._opencode.package,
            self._opencode.version or "",
            str(self._opencode.cache_dir.resolve()),
            self._opencode.docker_image,
            self._opencode.network,
            str(self._opencode.timeout_seconds),
        )

    def _container_base_url(self) -> str:
        if self._opencode.container_base_url:
            return self._opencode.container_base_url.rstrip("/")
        return translate_base_url_for_container(self._llm.base_url)

    def _run_docker(
        self,
        docker_command: list[str],
        *,
        timeout: int | float | None = None,
        env: dict[str, str] | None = None,
        keep_on_timeout: bool = False,
    ) -> CommandResult:
        subprocess_env = os.environ.copy()
        if env:
            subprocess_env.update(env)
        try:
            completed = subprocess.run(
                docker_command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=subprocess_env,
            )
            return CommandResult(
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                container_name=_extract_docker_container_name(docker_command),
            )
        except subprocess.TimeoutExpired as exc:
            container_name = _extract_docker_container_name(docker_command)
            if container_name and not keep_on_timeout:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            return CommandResult(
                exit_code=124,
                stdout=_decode_output(exc.stdout),
                stderr=_decode_output(exc.stderr),
                timed_out=True,
                container_name=container_name if keep_on_timeout else None,
            )
        except OSError as exc:
            return CommandResult(exit_code=127, stdout="", stderr=str(exc))


def create_solution_generator(config: AppConfig) -> SolutionGenerator:
    if config.benchmark.generator == "opencode":
        return OpenCodeGenerator(config)
    return DirectLlmGenerator(config)


def opencode_metadata_to_dict(
    metadata: OpenCodeRunMetadata | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata
    return asdict(metadata)


def translate_base_url_for_container(base_url: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    hostname = parsed.hostname
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        return base_url.rstrip("/")
    netloc = "host.docker.internal"
    if parsed.port is not None:
        netloc += f":{parsed.port}"
    if parsed.username or parsed.password:
        auth = parsed.username or ""
        if parsed.password:
            auth += f":{parsed.password}"
        netloc = f"{auth}@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _parse_opencode_usage(text: str) -> LlmUsage:
    totals = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
    }
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        _collect_usage(payload, totals)
    return LlmUsage(
        prompt_tokens=totals["prompt_tokens"],
        completion_tokens=totals["completion_tokens"],
        total_tokens=totals["total_tokens"],
        reasoning_tokens=totals["reasoning_tokens"],
    )


def _parse_opencode_error(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "error":
            continue
        error = payload.get("error")
        if isinstance(error, dict):
            data = error.get("data")
            if isinstance(data, dict) and data.get("message") is not None:
                return str(data["message"])
            if error.get("message") is not None:
                return str(error["message"])
            return json.dumps(error, sort_keys=True)
        return str(error)
    return None


def _opencode_session_missing_model_result(text: str) -> bool:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = payload.get("type")
        part = payload.get("part")
        if event_type == "tool_use":
            return False
        if isinstance(part, dict):
            if part.get("type") == "tool":
                return False
            if part.get("type") == "step-finish":
                tokens = part.get("tokens")
                if isinstance(tokens, dict) and any(
                    _optional_int(tokens.get(key))
                    for key in ("input", "output", "total", "reasoning")
                ):
                    return False
    return True


def _collect_usage(value: Any, totals: dict[str, int | None]) -> None:
    if isinstance(value, dict):
        for source, target in [
            ("prompt_tokens", "prompt_tokens"),
            ("input_tokens", "prompt_tokens"),
            ("input", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
            ("output_tokens", "completion_tokens"),
            ("output", "completion_tokens"),
            ("total_tokens", "total_tokens"),
            ("total", "total_tokens"),
            ("reasoning_tokens", "reasoning_tokens"),
            ("reasoning", "reasoning_tokens"),
        ]:
            number = _optional_int(value.get(source))
            if number is not None:
                totals[target] = (totals[target] or 0) + number
        for child in value.values():
            _collect_usage(child, totals)
    elif isinstance(value, list):
        for child in value:
            _collect_usage(child, totals)


def _build_agent_prompt_suffix(config: OpenCodeConfig) -> str:
    return (
        "Work non-interactively. Do not ask the user questions. "
        "Keep the solution focused and finish after the generated file is complete, "
        f"staying within {config.max_steps} tool steps."
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_cache_key(value: str) -> str:
    cleaned = []
    for char in value.strip():
        if char.isalnum() or char in {".", "-", "_"}:
            cleaned.append(char)
        else:
            cleaned.append("-")
    return "".join(cleaned).strip(".-_") or "unknown"


def _container_name(prefix: str, label: str, *, include_prefix: bool = True) -> str:
    safe_label = _safe_cache_key(label).lower()[:40]
    parts = ["csharp-llm-benchmark-opencode"]
    if include_prefix:
        parts.append(prefix)
    parts.extend([safe_label, uuid.uuid4().hex[:12]])
    return "-".join(parts)


def _extract_docker_container_name(command: list[str]) -> str | None:
    for index, value in enumerate(command):
        if value == "--name" and index + 1 < len(command):
            return command[index + 1]
    return None


def _last_non_empty_line(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line:
            return line
    return None


def _decode_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _public_files_list(task: Task) -> str:
    files = [
        public_file
        for public_file in task.public_files
        if not _is_generated_file(task, public_file)
    ]
    if not files:
        return "- (none)"
    return "\n".join(f"- `{public_file}`" for public_file in files)


def _is_generated_file(task: Task, public_file: str) -> bool:
    return Path(public_file).as_posix() == Path(task.generated_file).as_posix()


def _workspace_boundary() -> str:
    return (
        "Use only files available in the current workspace. Do not infer unseen "
        "files or read paths outside the current project."
    )


def _opencode_solution_rules() -> str:
    return SYSTEM_PROMPT.replace(
        "Return exactly one fenced ```csharp code block, with no text outside it.\n",
        "",
    ).strip()


def _task_contract(task: Task) -> str:
    return task.prompt.strip()


def _workspace_summary(task: Task) -> str:
    return (
        "Public support files available in the workspace:\n"
        f"{_public_files_list(task)}\n\n"
        f"{_workspace_boundary()}"
    )


def _workspace_generation_instructions(task: Task) -> str:
    return (
        "Workspace instructions:\n"
        f"- Create exactly the required generated file: `{task.generated_file}`.\n"
        "- The generated file is intentionally not present in the workspace; write "
        "it from the task contract instead of editing an existing source file.\n"
        "- Write the file directly in this workspace. Do not delegate the work to "
        "a subagent, background task, or separate planning task.\n"
        "- Do not create or modify any other source, project, or package files "
        "unless the task explicitly requires it.\n"
        "- Ensure the final code is valid C# for .NET 8."
    )


def _agent_prompt(task: Task, config: OpenCodeConfig) -> str:
    return "\n\n".join(
        [
            "You are generating a C# source file in a project workspace.",
            "Follow these solution rules:\n" + _opencode_solution_rules(),
            "Task:\n" + _task_contract(task),
            _workspace_summary(task),
            _workspace_generation_instructions(task),
            _build_agent_prompt_suffix(config),
        ]
    )
