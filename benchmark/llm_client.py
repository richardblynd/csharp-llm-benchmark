from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from benchmark.config import LlmConfig


SYSTEM_PROMPT = """You are an expert C# developer solving coding tasks.
Write clean, efficient C# code targeting .NET 10.
Return a complete C# source file that compiles as-is.
Include required using directives for .NET framework types, or fully qualify those types.
Output ONLY the raw C# code inside a markdown block.
Do not use external libraries.
Do not include a namespace.
Do not include comments in the generated code.
Do not include explanations, greetings, or pleasantries."""


@dataclass(frozen=True)
class LlmResponse:
    content: str
    payload: dict[str, Any]
    raw_json: dict[str, Any]
    response_time_seconds: float
    usage: LlmUsage


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


class LlmClient:
    def __init__(self, config: LlmConfig):
        self.config = config

    def complete(self, user_prompt: str) -> LlmResponse:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "seed": self.config.seed,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        started_at = time.perf_counter()
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                raw_json = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP error {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach LLM server: {exc.reason}") from exc

        response_time_seconds = time.perf_counter() - started_at
        content = str(raw_json["choices"][0]["message"]["content"])
        return LlmResponse(
            content=content,
            payload=payload,
            raw_json=raw_json,
            response_time_seconds=response_time_seconds,
            usage=_parse_usage(raw_json),
        )


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
        code = _extract_unfenced_code(response_text)
        if code is None:
            return ExtractedCode(
                code=None,
                warnings=tuple(warnings),
                error="Could not find reliable C# code in the LLM response.",
            )
        warnings.append("Extracted code from an unfenced response.")

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
        rf"\bpublic\s+class\s+{re.escape(required_public_class)}\b", code
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


def _extract_unfenced_code(text: str) -> str | None:
    starts = [
        r"\busing\b",
        r"\bpublic\s+class\s+Solution\b",
        r"\bpublic\s+static\b",
        r"\bclass\s+Solution\b",
        r"\bclass\b",
        r"\brecord\b",
        r"\bstatic\b",
    ]
    for pattern in starts:
        match = re.search(pattern, text)
        if match:
            return text[match.start() :]
    return None


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


def _parse_usage(raw_json: dict[str, Any]) -> LlmUsage:
    usage = raw_json.get("usage")
    if not isinstance(usage, dict):
        return LlmUsage()

    completion_details = usage.get("completion_tokens_details")
    reasoning_tokens = None
    if isinstance(completion_details, dict):
        reasoning_tokens = _as_int(completion_details.get("reasoning_tokens"))

    return LlmUsage(
        prompt_tokens=_as_int(usage.get("prompt_tokens")),
        completion_tokens=_as_int(usage.get("completion_tokens")),
        total_tokens=_as_int(usage.get("total_tokens")),
        reasoning_tokens=reasoning_tokens,
    )


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
