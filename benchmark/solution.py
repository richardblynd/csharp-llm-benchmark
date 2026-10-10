from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedCode:
    code: str | None
    warnings: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class LlmUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None


def extract_solution_code(
    response_text: str,
    *,
    required_public_class: str | None = "Solution",
) -> ExtractedCode:
    warnings: list[str] = []

    fenced = _extract_fenced_code(response_text)
    if fenced is not None:
        code, language = fenced
        if response_text.strip() != _first_fence_text(response_text).strip():
            warnings.append("Ignored text outside the first markdown code block.")
        if language and language.lower() not in {"csharp", "cs"}:
            warnings.append(f"Used a non-csharp markdown block: {language}.")
    else:
        code = response_text

    code = code.strip()
    if not code:
        return ExtractedCode(
            code=None,
            warnings=tuple(warnings),
            error="Extracted code was empty.",
        )

    if _declares_namespace(code):
        return ExtractedCode(
            code=None,
            warnings=tuple(warnings),
            error="Generated code declares a namespace, which is not allowed.",
        )

    if required_public_class and not re.search(
        _public_class_declaration_pattern(required_public_class),
        code,
    ):
        return ExtractedCode(
            code=None,
            warnings=tuple(warnings),
            error=f"Generated code does not declare public class {required_public_class}.",
        )

    return ExtractedCode(code=code + "\n", warnings=tuple(warnings))


def _extract_fenced_code(text: str) -> tuple[str, str] | None:
    matches = list(re.finditer(r"```([A-Za-z0-9_-]*)\s*\n(.*?)```", text, re.S))
    if not matches:
        return None
    csharp_match = next(
        (
            match
            for match in matches
            if match.group(1).strip().lower() in {"csharp", "cs"}
        ),
        None,
    )
    match = csharp_match or matches[0]
    return match.group(2), match.group(1).strip()


def _first_fence_text(text: str) -> str:
    match = re.search(r"```[A-Za-z0-9_-]*\s*\n.*?```", text, re.S)
    return match.group(0) if match else text


def _public_class_declaration_pattern(class_name: str) -> str:
    return (
        rf"\bpublic\s+"
        rf"(?:[A-Za-z_][A-Za-z0-9_]*\s+)*"
        rf"class\s+{re.escape(class_name)}\b"
    )


def _declares_namespace(code: str) -> bool:
    declaration = re.compile(
        r"\bnamespace\s+"
        r"[A-Za-z_][A-Za-z0-9_]*"
        r"(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_]*)*"
        r"\s*(?:[;{])"
    )
    return declaration.search(_strip_csharp_comments_and_literals(code)) is not None


def _strip_csharp_comments_and_literals(code: str) -> str:
    chars = list(code)
    index = 0
    length = len(chars)

    while index < length:
        current = chars[index]
        next_char = chars[index + 1] if index + 1 < length else ""

        if current == "/" and next_char == "/":
            index = _blank_until(chars, index, "\n")
            continue
        if current == "/" and next_char == "*":
            index = _blank_block_comment(chars, index)
            continue
        if _starts_csharp_string(chars, index):
            index = _blank_csharp_string(chars, index)
            continue
        if current == "'":
            index = _blank_csharp_char_literal(chars, index)
            continue

        index += 1

    return "".join(chars)


def _blank_until(chars: list[str], index: int, terminator: str) -> int:
    while index < len(chars) and chars[index] != terminator:
        chars[index] = " "
        index += 1
    return index


def _blank_block_comment(chars: list[str], index: int) -> int:
    chars[index] = " "
    chars[index + 1] = " "
    index += 2
    while index < len(chars):
        if (
            chars[index] == "*"
            and index + 1 < len(chars)
            and chars[index + 1] == "/"
        ):
            chars[index] = " "
            chars[index + 1] = " "
            return index + 2
        if chars[index] != "\n":
            chars[index] = " "
        index += 1
    return index


def _starts_csharp_string(chars: list[str], index: int) -> bool:
    current = chars[index]
    next_char = chars[index + 1] if index + 1 < len(chars) else ""
    third_char = chars[index + 2] if index + 2 < len(chars) else ""

    return (
        current == '"'
        or (current == "@" and next_char == '"')
        or (current == "$" and next_char == '"')
        or (current == "$" and next_char == "@" and third_char == '"')
        or (current == "@" and next_char == "$" and third_char == '"')
    )


def _blank_csharp_string(chars: list[str], index: int) -> int:
    is_interpolated_verbatim = (
        index + 2 < len(chars)
        and chars[index] in {"@", "$"}
        and chars[index + 1] in {"@", "$"}
        and chars[index] != chars[index + 1]
        and chars[index + 2] == '"'
    )
    is_prefixed = (
        index + 1 < len(chars)
        and chars[index] in {"@", "$"}
        and chars[index + 1] == '"'
    )
    quote_index = (
        index + 2
        if is_interpolated_verbatim
        else index + 1
        if is_prefixed
        else index
    )
    is_verbatim = chars[index] == "@" or is_interpolated_verbatim

    while index <= quote_index:
        chars[index] = " "
        index += 1

    while index < len(chars):
        if chars[index] == '"':
            chars[index] = " "
            if is_verbatim and index + 1 < len(chars) and chars[index + 1] == '"':
                chars[index + 1] = " "
                index += 2
                continue
            return index + 1
        if not is_verbatim and chars[index] == "\\" and index + 1 < len(chars):
            chars[index] = " "
            chars[index + 1] = " "
            index += 2
            continue
        if chars[index] != "\n":
            chars[index] = " "
        index += 1
    return index


def _blank_csharp_char_literal(chars: list[str], index: int) -> int:
    chars[index] = " "
    index += 1
    while index < len(chars):
        if chars[index] == "\\" and index + 1 < len(chars):
            chars[index] = " "
            chars[index + 1] = " "
            index += 2
            continue
        if chars[index] == "'":
            chars[index] = " "
            return index + 1
        if chars[index] != "\n":
            chars[index] = " "
        index += 1
    return index


