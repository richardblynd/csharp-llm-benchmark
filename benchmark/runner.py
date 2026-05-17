from __future__ import annotations

import json
import io
import shutil
import subprocess
import tarfile
import tempfile
import threading
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from benchmark.config import DockerConfig
from benchmark.llm_client import ExtractedCode, LlmUsage
from benchmark.tasks import Task


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def combined_output(self) -> str:
        return (self.stdout + "\n" + self.stderr).strip()


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    status: str
    llm_response_time_seconds: float
    llm_usage: LlmUsage
    workdir: str | None
    build: CommandResult | None
    test: CommandResult | None
    passed_tests: tuple[str, ...]
    failed_tests: tuple[str, ...]
    extraction_warnings: tuple[str, ...]
    extraction_error: str | None = None
    infrastructure_error: str | None = None


class DockerRunner:
    def __init__(self, config: DockerConfig):
        self.config = config
        self._active_containers: set[str] = set()
        self._lock = threading.Lock()
        self._cancelled = False

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            container_names = tuple(self._active_containers)
        for container_name in container_names:
            self._remove_container(container_name)

    def evaluate(
        self,
        task: Task,
        extracted_code: ExtractedCode,
        *,
        artifact_dir: Path,
        llm_response_time_seconds: float,
        llm_usage: LlmUsage,
    ) -> TaskRunResult:
        if extracted_code.code is None:
            return TaskRunResult(
                task_id=task.id,
                status="extraction_error",
                llm_response_time_seconds=llm_response_time_seconds,
                llm_usage=llm_usage,
                workdir=None,
                build=None,
                test=None,
                passed_tests=(),
                failed_tests=(),
                extraction_warnings=extracted_code.warnings,
                extraction_error=extracted_code.error,
            )

        with tempfile.TemporaryDirectory(
            prefix=f"{task.id}-",
            dir=artifact_dir,
        ) as temp_dir:
            workdir = Path(temp_dir)
            self._prepare_workspace(task, extracted_code.code, workdir)
            self._snapshot_workspace(workdir, artifact_dir / "workspace")

            container_name = f"csharp-llm-benchmark-{workdir.name}"
            container_workdir = f"/workspace/{workdir.name}"
            self._register_container(container_name)
            create = self._create_container(container_name)
            if create.exit_code != 0:
                (artifact_dir / "build.log").write_text(
                    create.combined_output + "\n", encoding="utf-8"
                )
                self._remove_container(container_name)
                self._unregister_container(container_name)
                return self._infrastructure_result(
                    task,
                    workdir,
                    create,
                    "Docker could not create the evaluation container.",
                    llm_response_time_seconds=llm_response_time_seconds,
                    llm_usage=llm_usage,
                )

            try:
                if self._is_cancelled():
                    return self._infrastructure_result(
                        task,
                        workdir,
                        create,
                        "Evaluation was cancelled.",
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )

                setup = self._copy_workspace_to_container(
                    container_name,
                    workdir,
                    container_workdir,
                )
                if setup.exit_code != 0:
                    (artifact_dir / "build.log").write_text(
                        setup.combined_output + "\n", encoding="utf-8"
                    )
                    return self._infrastructure_result(
                        task,
                        workdir,
                        setup,
                        "Docker could not copy the workspace into the container.",
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )

                build = self._exec_in_container(
                    container_name,
                    container_workdir,
                    task.build_command,
                )
                (artifact_dir / "build.log").write_text(
                    build.combined_output + "\n", encoding="utf-8"
                )

                if build.exit_code in {125, 126, 127}:
                    return self._infrastructure_result(
                        task,
                        workdir,
                        build,
                        "Docker or the evaluation image failed before build could run.",
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )
                if build.timed_out:
                    return self._infrastructure_result(
                        task,
                        workdir,
                        build,
                        "Build command timed out.",
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )
                if build.exit_code != 0:
                    return TaskRunResult(
                        task_id=task.id,
                        status="build_failed",
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                        workdir=str(workdir),
                        build=build,
                        test=None,
                        passed_tests=(),
                        failed_tests=(),
                        extraction_warnings=extracted_code.warnings,
                    )

                test = self._exec_in_container(
                    container_name,
                    container_workdir,
                    task.test_command,
                )
                (artifact_dir / "test.log").write_text(
                    test.combined_output + "\n", encoding="utf-8"
                )

                if test.exit_code in {125, 126, 127}:
                    return self._infrastructure_result(
                        task,
                        workdir,
                        build,
                        "Docker or the evaluation image failed before tests could run.",
                        test,
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )
                if test.timed_out:
                    return self._infrastructure_result(
                        task,
                        workdir,
                        build,
                        "Test command timed out.",
                        test,
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )

                copy_results = self._copy_results_from_container(
                    container_name,
                    container_workdir,
                    workdir,
                )
                if copy_results.exit_code != 0:
                    return self._infrastructure_result(
                        task,
                        workdir,
                        build,
                        "Docker could not copy test results out of the container.",
                        test,
                        llm_response_time_seconds=llm_response_time_seconds,
                        llm_usage=llm_usage,
                    )

                passed, failed = parse_trx_results(workdir / "TestResults")
                status = "passed" if test.exit_code == 0 else "tests_failed"
                return TaskRunResult(
                    task_id=task.id,
                    status=status,
                    llm_response_time_seconds=llm_response_time_seconds,
                    llm_usage=llm_usage,
                    workdir=str(workdir),
                    build=build,
                    test=test,
                    passed_tests=tuple(sorted(passed)),
                    failed_tests=tuple(sorted(failed)),
                    extraction_warnings=extracted_code.warnings,
                )
            finally:
                self._remove_container(container_name)
                self._unregister_container(container_name)

    def _register_container(self, container_name: str) -> None:
        with self._lock:
            self._active_containers.add(container_name)

    def _unregister_container(self, container_name: str) -> None:
        with self._lock:
            self._active_containers.discard(container_name)

    def _is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def _prepare_workspace(self, task: Task, code: str, workdir: Path) -> None:
        for public_file in task.public_files:
            source = task.template_dir / public_file
            destination = workdir / public_file
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        generated_path = workdir / task.generated_file
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text(code, encoding="utf-8")
        (workdir / "Directory.Build.targets").write_text(
            "\n".join(
                [
                    '<Project>',
                    '  <ItemGroup Condition="\'$(MSBuildProjectName)\' == \'Solution\'">',
                    '    <Compile Remove="tests/**/*.cs" />',
                    '  </ItemGroup>',
                    '</Project>',
                    '',
                ]
            ),
            encoding="utf-8",
        )

        tests_destination = workdir / "tests"
        tests_destination.mkdir(parents=True, exist_ok=True)
        for hidden_test in task.hidden_tests:
            shutil.copy2(task.tests_dir / hidden_test, tests_destination / hidden_test)

    def _snapshot_workspace(self, workdir: Path, destination: Path) -> None:
        if destination.exists():
            shutil.rmtree(destination)
        ignore = shutil.ignore_patterns("bin", "obj", "TestResults", ".tmp")
        shutil.copytree(workdir, destination, ignore=ignore)

    def _create_container(self, container_name: str) -> CommandResult:
        docker_command = [
            "docker",
            "create",
            "--name",
            container_name,
            "--network",
            self.config.network,
        ]
        if self.config.read_only:
            docker_command.append("--read-only")
        for capability in self.config.cap_drop:
            docker_command.extend(["--cap-drop", capability])
        docker_command.extend(
            [
                "--pids-limit",
                str(self.config.pids_limit),
                "--memory",
                self.config.memory_limit,
                "--cpus",
                self.config.cpus,
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
                "--tmpfs",
                "/workspace:rw,nosuid,nodev,size=256m,mode=1777",
                "--env",
                "DOTNET_CLI_HOME=/tmp",
                "--env",
                "NUGET_PACKAGES=/nuget/packages",
                "--workdir",
                "/workspace",
                self.config.image,
                "/bin/sh",
                "-lc",
                "sleep infinity",
            ]
        )
        create = self._run_docker_command(docker_command)
        if create.exit_code != 0:
            return create
        return self._run_docker_command(["docker", "start", container_name])

    def _copy_workspace_to_container(
        self,
        container_name: str,
        workdir: Path,
        container_workdir: str,
    ) -> CommandResult:
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            tar.add(workdir, arcname=workdir.name)
        copy = self._run_docker_command(
            [
                "docker",
                "exec",
                "-i",
                "--user",
                "root",
                "--workdir",
                "/workspace",
                container_name,
                "tar",
                "-xf",
                "-",
                "--no-same-owner",
                "-C",
                "/workspace",
            ],
            input_data=archive.getvalue(),
        )
        if copy.exit_code != 0:
            return copy
        return self._run_docker_command(
            [
                "docker",
                "exec",
                "--user",
                "root",
                container_name,
                "chmod",
                "-R",
                "a+rwX",
                container_workdir,
            ]
        )

    def _exec_in_container(
        self,
        container_name: str,
        container_workdir: str,
        command: str,
    ) -> CommandResult:
        return self._run_docker_command(
            [
                "docker",
                "exec",
                "--user",
                "benchmark",
                "--workdir",
                container_workdir,
                container_name,
                "/bin/sh",
                "-lc",
                command,
            ],
            timeout=self.config.timeout_seconds,
        )

    def _copy_results_from_container(
        self,
        container_name: str,
        container_workdir: str,
        workdir: Path,
    ) -> CommandResult:
        destination = workdir / "TestResults"
        if destination.exists():
            shutil.rmtree(destination)
        completed = subprocess.run(
            [
                "docker",
                "exec",
                "--user",
                "benchmark",
                "--workdir",
                container_workdir,
                container_name,
                "tar",
                "-cf",
                "-",
                "TestResults",
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if completed.returncode != 0:
            return CommandResult(
                exit_code=completed.returncode,
                stdout=_decode_output(completed.stdout),
                stderr=_decode_output(completed.stderr),
            )

        try:
            with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as tar:
                workdir_root = workdir.resolve()
                for member in tar.getmembers():
                    target = (workdir / member.name).resolve()
                    if workdir_root not in {target, *target.parents}:
                        return CommandResult(
                            exit_code=1,
                            stdout="",
                            stderr=f"Refusing to extract unsafe path: {member.name}",
                        )
                tar.extractall(workdir)
        except tarfile.TarError as exc:
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=f"Could not extract test results: {exc}",
            )
        return CommandResult(exit_code=0, stdout="", stderr="")

    def _remove_container(self, container_name: str) -> None:
        self._run_docker_command(["docker", "rm", "-f", container_name], timeout=10)

    def _run_docker_command(
        self,
        docker_command: list[str],
        *,
        timeout: int | float | None = None,
        input_data: bytes | None = None,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                docker_command,
                check=False,
                capture_output=True,
                input=input_data,
                text=input_data is None,
                timeout=timeout,
            )
            return CommandResult(
                exit_code=completed.returncode,
                stdout=_decode_output(completed.stdout),
                stderr=_decode_output(completed.stderr),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=124,
                stdout=_decode_output(exc.stdout),
                stderr=_decode_output(exc.stderr),
                timed_out=True,
            )
        except OSError as exc:
            return CommandResult(
                exit_code=127,
                stdout="",
                stderr=str(exc),
            )

    def _infrastructure_result(
        self,
        task: Task,
        workdir: Path,
        build: CommandResult,
        message: str,
        test: CommandResult | None = None,
        *,
        llm_response_time_seconds: float,
        llm_usage: LlmUsage,
    ) -> TaskRunResult:
        return TaskRunResult(
            task_id=task.id,
            status="infrastructure_error",
            llm_response_time_seconds=llm_response_time_seconds,
            llm_usage=llm_usage,
            workdir=str(workdir),
            build=build,
            test=test,
            passed_tests=(),
            failed_tests=(),
            extraction_warnings=(),
            infrastructure_error=message,
        )


def parse_trx_results(results_dir: Path) -> tuple[set[str], set[str]]:
    passed: set[str] = set()
    failed: set[str] = set()
    if not results_dir.exists():
        return passed, failed

    for trx_file in results_dir.rglob("*.trx"):
        try:
            root = ET.parse(trx_file).getroot()
        except ET.ParseError:
            continue
        for result in root.iter():
            if not result.tag.endswith("UnitTestResult"):
                continue
            test_name = result.attrib.get("testName") or result.attrib.get("testId")
            outcome = result.attrib.get("outcome")
            if not test_name:
                continue
            normalized = _normalize_test_name(test_name)
            if outcome == "Passed":
                passed.add(normalized)
            else:
                failed.add(normalized)
    return passed, failed


def write_result_json(path: Path, result: TaskRunResult) -> None:
    path.write_text(
        json.dumps(
            {
                "task_id": result.task_id,
                "status": result.status,
                "llm_response_time_seconds": result.llm_response_time_seconds,
                "llm_usage": asdict(result.llm_usage),
                "workdir": result.workdir,
                "passed_tests": list(result.passed_tests),
                "failed_tests": list(result.failed_tests),
                "extraction_warnings": list(result.extraction_warnings),
                "extraction_error": result.extraction_error,
                "infrastructure_error": result.infrastructure_error,
                "build_exit_code": result.build.exit_code if result.build else None,
                "test_exit_code": result.test.exit_code if result.test else None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _normalize_test_name(test_name: str) -> str:
    short_name = test_name.split(".")[-1]
    short_name = short_name.split("(")[0]
    return short_name.strip()


def _decode_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output
