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

    if re.search(r"\bnamespace\b", code):
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
