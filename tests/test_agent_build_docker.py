"""Opt-in first-build checks using the actual generator container configuration."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid

from benchmark.config import AppConfig, OpenCodeConfig, PiConfig
from benchmark.generation import OpenCodeGenerator, PiGenerator
from benchmark.tasks import load_tasks
from benchmark.workspace import copy_public_files


@unittest.skipUnless(os.environ.get("BENCHMARK_DOCKER_TESTS") == "1",
                     "Set BENCHMARK_DOCKER_TESTS=1 to run real Docker evaluations")
class AgentFirstBuildDockerTests(unittest.TestCase):
    def test_first_build_succeeds_with_fresh_agent_home(self):
        task = load_tasks(tasks_root=Path(__file__).resolve().parents[1] / "tasks", suite="evolution")[0]
        for generator in ("pi", "opencode"):
            with self.subTest(generator=generator):
                self._check_build(task, generator, create=False)

    def test_web_builds_repeatedly_on_host_workspace(self):
        task = load_tasks(tasks_root=Path(__file__).resolve().parents[1] / "tasks",
                          suite="evolution", difficulty="medium")[0]
        for generator in ("pi", "opencode"):
            for create in (False, True):
                for project_dir in (".", "apps/reservations"):
                    with self.subTest(generator=generator, create=create, project_dir=project_dir):
                        self._check_build(task, generator, create=create, repeat=True,
                                          project_dir=project_dir)

    def _check_build(self, task, generator, *, create, repeat=False, project_dir="."):
        # /tmp in WSL uses the Linux filesystem and masks Windows mount failures.
        # Keep the actual bind-mounted workspace on the checkout's filesystem.
        fixture_root = Path(__file__).resolve().parents[1] / ".cache/agent-build-tests"
        fixture_root.mkdir(parents=True, exist_ok=True)
        config = AppConfig(opencode=OpenCodeConfig(version="test", network="none",
                                                  cache_dir=fixture_root / "opencode-cache"),
                           pi=PiConfig(version="test", network="none",
                                       cache_dir=fixture_root / "pi-cache"))
        with tempfile.TemporaryDirectory(dir=fixture_root) as directory:
            root = Path(directory)
            workspace, home, install = root / "workspace", root / "home", root / "install"
            copy_public_files(task, workspace / project_dir)
            home.mkdir()
            binary = install / "node_modules/.bin/pi"
            binary.parent.mkdir(parents=True)
            binary.touch()
            name = f"benchmark-first-build-{uuid.uuid4().hex[:12]}"
            if generator == "pi":
                instance = PiGenerator(config)
                with patch.object(instance, "_pi_install_dir", return_value=install):
                    command = ["docker", "create" if create else "run"]
                    if not create:
                        command.append("--rm")
                    command.extend(instance._pi_docker_command(
                        workspace, home, container_name=name, create=create))
            else:
                instance = OpenCodeGenerator(config)
                with patch.object(instance, "_opencode_install_dir", return_value=install):
                    command = instance._opencode_docker_command(task, workspace, home,
                                                               container_name=name, create=create)
            # Replace only agent invocation. User, environment and mounts stay real.
            project = Path(project_dir) / task.build_project
            build = f"dotnet build {shlex.quote(project.as_posix())} --configuration Release"
            command[-1] = f"set -eu\ncd /workspace\n{build}"
            if repeat:
                apphost = project.parent / "bin/Release/net8.0" / project.stem
                command[-1] += f"\n{build}\ntest -x {shlex.quote(apphost.as_posix())}"
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if create:
                    result = subprocess.run(["docker", "start", "--attach", name],
                                            capture_output=True, text=True, timeout=60)
                    state = subprocess.run(["docker", "inspect", "--format", "{{.State.ExitCode}}", name],
                                           capture_output=True, text=True, timeout=10)
                    self.assertEqual(state.returncode, 0, state.stderr)
                    self.assertEqual(state.stdout.strip(), "0", result.stdout + result.stderr)
                self.assertFalse((home / ".nuget").exists(), "NuGet state must stay off the host bind mount")
                for output_name in ("bin", "obj"):
                    self.assertFalse(any((workspace / project.parent / output_name).rglob("*")),
                                     "Build outputs must stay off the host bind mount")
                print(f"{generator}: {project.as_posix()} build succeeded (precreated={create})", flush=True)
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
