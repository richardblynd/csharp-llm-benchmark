from __future__ import annotations

from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    return parse_yaml(path.read_text(encoding="utf-8"))


def parse_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by this project.

    Supported features: nested mappings, scalar values, and lists of scalars.
    This keeps the benchmark bootstrap dependency-free while still allowing
    human-friendly config and task files.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        raw_line = lines[index]
        index += 1
        line_without_comment = _strip_comment(raw_line)
        if not line_without_comment.strip():
            continue

        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        line = line_without_comment.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError(f"Invalid indentation near line: {raw_line}")

        parent = stack[-1][1]

        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"List item without list parent near line: {raw_line}")
            parent.append(_parse_scalar(line[2:].strip()))
            continue

        if ":" not in line:
            raise ValueError(f"Expected key/value near line: {raw_line}")

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not isinstance(parent, dict):
            raise ValueError(f"Mapping entry without mapping parent near line: {raw_line}")

        if value:
            parent[key] = _parse_scalar(value)
            continue

        next_container: Any = {}
        next_line = _peek_next_content(lines, index)
        if next_line is not None:
            next_indent, next_content = next_line
            if next_indent > indent and next_content.startswith("- "):
                next_container = []
        parent[key] = next_container
        stack.append((indent, next_container))

    return root


def _peek_next_content(lines: list[str], start: int) -> tuple[int, str] | None:
    for raw_line in lines[start:]:
        line_without_comment = _strip_comment(raw_line)
        if not line_without_comment.strip():
            continue
        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        return indent, line_without_comment.strip()
    return None


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return value
