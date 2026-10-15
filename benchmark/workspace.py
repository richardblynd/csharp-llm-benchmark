"""Capture a project delivery and reconstruct it using trusted project files."""
from __future__ import annotations

from dataclasses import dataclass
import difflib
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmark.tasks import Task


@dataclass(frozen=True)
class ProjectFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class ProjectSnapshot:
    files: tuple[ProjectFile, ...]
    deleted_files: tuple[str, ...]
    task_fingerprint: str


def relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError(f"Unsafe project path: {value}")
    if str(path) == ".":
        raise ValueError(f"Unsafe project path: {value}")
    return path.as_posix()


def is_editable(task: Task, path: str) -> bool:
    # Only C# sources can change in the pilot; project/build/test files are trusted.
    path = relative_path(path)
    return (path.endswith(".cs") and path.startswith("src/")
            and any(fnmatch.fnmatchcase(path, pattern) for pattern in task.editable_files))


def _linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _checked_file(root: Path, name: str) -> Path:
    name = relative_path(name)
    path = root / name
    for current in (path, *path.parents):
        if current == root:
            break
        if _linked(current):
            raise ValueError(f"Linked project path is not allowed: {name}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Project path escapes workspace: {name}")
    return path


def copy_public_files(task: Task, destination: Path) -> None:
    for name in task.public_files:
        source = _checked_file(task.template_dir, name)
        target = _checked_file(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def task_fingerprint(task: Task) -> str:
    payload = {
        "id": task.id, "suite": task.suite, "version": task.version,
        "prompt": task.prompt, "score": {
            "compile": task.score.compile, "feature": task.score.tests,
            "regression": task.score.regression,
        },
        "editable_files": task.editable_files, "build_project": task.build_project,
        "build_command": task.build_command,
        "test_groups": [(g.name, g.build_command, g.test_command) for g in task.test_groups],
        "public": {name: hashlib.sha256(_checked_file(task.template_dir, name).read_bytes()).hexdigest()
                   for name in task.public_files},
        "hidden": {name: hashlib.sha256(_checked_file(task.tests_dir, name).read_bytes()).hexdigest()
                   for name in task.hidden_tests},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def capture_project(task: Task, workspace: Path, artifact_dir: Path | None = None) -> ProjectSnapshot:
    public = {relative_path(name) for name in task.public_files}
    deleted = []
    for name in sorted(public):
        path = _checked_file(workspace, name)
        if is_editable(task, name):
            if not path.is_file():
                deleted.append(name)
        elif not path.is_file() or path.read_bytes() != _checked_file(task.template_dir, name).read_bytes():
            raise ValueError(f"Immutable public file was changed or removed: {name}")

    files = []
    sources = _checked_file(workspace, "src")
    for directory, dirs, names in os.walk(sources, followlinks=False):
        for name in (*dirs, *names):
            path = Path(directory) / name
            if _linked(path):
                raise ValueError(f"Linked project path is not allowed: {path.relative_to(workspace)}")
        dirs[:] = [name for name in dirs if name not in {"bin", "obj", ".git"}]
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(workspace).as_posix()
            if is_editable(task, relative):
                files.append(ProjectFile(relative, path.read_bytes()))
            elif relative not in public:
                raise ValueError(f"Unexpected project file: {relative}")
    snapshot = ProjectSnapshot(tuple(sorted(files, key=lambda f: f.path)), tuple(deleted), task_fingerprint(task))
    if artifact_dir is not None:
        _write_delivery(task, snapshot, artifact_dir)
    return snapshot


def restore_project(task: Task, snapshot: ProjectSnapshot, destination: Path) -> None:
    if snapshot.task_fingerprint != task_fingerprint(task):
        raise ValueError("Project delivery belongs to a different task contract")
    copy_public_files(task, destination)
    seen = set()
    for name in snapshot.deleted_files:
        if not is_editable(task, name) or name not in task.public_files:
            raise ValueError(f"Invalid deleted project file: {name}")
        _checked_file(destination, name).unlink()
    for file in snapshot.files:
        if not is_editable(task, file.path) or file.path in seen or file.path in snapshot.deleted_files:
            raise ValueError(f"Invalid delivered project file: {file.path}")
        seen.add(file.path)
        path = _checked_file(destination, file.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file.content)


def _write_delivery(task: Task, snapshot: ProjectSnapshot, artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"task_fingerprint": snapshot.task_fingerprint, "deleted_files": snapshot.deleted_files,
                "files": {file.path: hashlib.sha256(file.content).hexdigest() for file in snapshot.files}}
    diff = []
    delivered = {file.path: file.content for file in snapshot.files}
    for name in sorted(set(delivered) | set(snapshot.deleted_files)):
        before = (task.template_dir / name).read_bytes() if name in task.public_files else b""
        after = delivered.get(name, b"")
        diff.extend(difflib.unified_diff(before.decode("utf-8", errors="replace").splitlines(True),
                                         after.decode("utf-8", errors="replace").splitlines(True),
                                         fromfile=f"starter/{name}", tofile=f"delivery/{name}"))
        if name in delivered:
            path = _checked_file(artifact_dir / "delivery", name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(after)
    (artifact_dir / "delivery.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "changes.diff").write_text("".join(diff), encoding="utf-8")
