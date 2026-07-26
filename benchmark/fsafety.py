"""File-system safety helpers shared across the benchmark package."""
from __future__ import annotations

import shutil
from pathlib import Path


def safe_rmtree(
    path: Path,
    *,
    safe_parent: Path | None = None,
    ignore_errors: bool = False,
) -> None:
    """Safely remove a directory tree, verifying the target is within *safe_parent*.

    Raises ``ValueError`` if *path* resolves outside the allowed parent,
    preventing accidental deletion of project files when output_dir or task_dir
    are misconfigured.
    """
    abs_path = path.resolve()
    if safe_parent is not None:
        try:
            abs_path.relative_to(safe_parent.resolve())
        except ValueError:
            raise ValueError(
                f"Refusing rmtree: {abs_path} is outside allowed parent {safe_parent.resolve()}"
            )
    shutil.rmtree(abs_path, ignore_errors=ignore_errors)


def cache_safety_root(abs_path: Path) -> Path | None:
    """Return the safety root for a cache install path, or ``None`` to skip.

    The root is determined by looking at the first component of *abs_path* that
    matches known cache directory basenames (e.g. ``.cache``, ``opencode``,
    ``pi-coding-agent``).  This allows _ensure_is_directory to confine its
    unlink operations to a safe subtree.
    """
    CACHE_DIRS = {".cache", "opencode", "pi-coding-agent"}
    for part in abs_path.parts:
        if part in CACHE_DIRS:
            return Path(*abs_path.parts[: abs_path.parts.index(part) + 1])
    return None
