from __future__ import annotations

import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class LmStudioModelMeta:
    """Metadata for one model, sourced from the LM Studio local API.

    All fields are optional: a failed/absent lookup yields an empty meta so
    callers can fall back to config values without special-casing errors.
    """

    size_bytes: int | None = None
    quantization: str | None = None
    params_string: str | None = None


def derive_base_root(base_url: str) -> str:
    """Return the server root for an OpenAI-style base URL.

    "http://localhost:1234/v1" -> "http://localhost:1234"
    """
    stripped = base_url.rstrip("/")
    if stripped.endswith("/v1"):
        return stripped[: -len("/v1")]
    return stripped


def _is_private_ipv4(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4 or not all(part.isdigit() for part in parts):
        return False
    first, second = int(parts[0]), int(parts[1])
    return (
        first == 127
        or first == 10
        or (first == 172 and 16 <= second <= 31)
        or (first == 192 and second == 168)
    )


def is_local_server(base_url: str) -> bool:
    """Heuristic gate: only talk to hosts that plausibly run LM Studio.

    Allows loopback, RFC-1918 private ranges and single-label/local
    hostnames (typical LAN setups such as http://192.168.x.y:1234). Public
    dotted hostnames (e.g. api.openai.com) are treated as remote so we never
    point the metadata call at a cloud endpoint.
    """
    try:
        hostname = (urlparse(base_url).hostname or "").rstrip(".")
    except ValueError:
        return False
    if not hostname:
        return False
    lowered = hostname.lower()
    if lowered in {"localhost", "::1"} or lowered.startswith("127."):
        return True
    if _is_private_ipv4(hostname):
        return True
    if "." not in hostname:
        # Single-label LAN/mDNS name (e.g. "lmsrv") — assume local.
        return True
    return lowered.endswith((".local", ".lan"))


def fetch_models(
    base_root: str, api_key: str | None = None, timeout_seconds: int = 10
) -> list[dict[str, Any]]:
    """GET {base_root}/api/v1/models and return the model entries.

    Fails soft: any transport/HTTP/parse problem yields an empty list with a
    warning on stderr (never raises).
    """
    url = f"{derive_base_root(base_root)}/api/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, socket.timeout):
        print(
            f"Warning: LM Studio metadata request timed out after "
            f"{timeout_seconds}s ({url}). Continuing without model size/quantization.",
            file=sys.stderr,
        )
        return []
    except urllib.error.HTTPError as exc:
        details = ""
        try:
            details = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        print(
            f"Warning: LM Studio metadata endpoint returned HTTP {exc.code} "
            f"({url}). Is the server running a recent LM Studio version? "
            f"{details}".strip(),
            file=sys.stderr,
        )
        return []
    except (urllib.error.URLError, OSError) as exc:
        print(
            f"Warning: could not reach LM Studio metadata endpoint at {url} "
            f"({exc}). Continuing without model size/quantization.",
            file=sys.stderr,
        )
        return []

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        print(
            f"Warning: unexpected response shape from {url}; "
            "continuing without model metadata.",
            file=sys.stderr,
        )
        return []
    return [entry for entry in models if isinstance(entry, dict)]


def match_model(
    models: list[dict[str, Any]],
    model: str | None = None,
    model_label: str | None = None,
) -> dict[str, Any] | None:
    """Find the library entry for a model by key or display name.

    Matching order per candidate identity: exact `key`, casefolded `key`,
    casefolded `display_name`. Candidates are tried in this order:
    `model` first (the API id), then `model_label` (user-facing label).
    """
    candidates = [value for value in (model, model_label) if value]
    for candidate in candidates:
        exact_key = next(
            (entry for entry in models if entry.get("key") == candidate), None
        )
        if exact_key is not None:
            return exact_key
        folded = candidate.strip().casefold()
        by_key = next(
            (
                entry
                for entry in models
                if str(entry.get("key", "")).strip().casefold() == folded
            ),
            None,
        )
        if by_key is not None:
            return by_key
    for candidate in candidates:
        folded = candidate.strip().casefold()
        by_name = next(
            (
                entry
                for entry in models
                if str(entry.get("display_name", ""))
                .strip()
                .casefold()
                == folded
            ),
            None,
        )
        if by_name is not None:
            return by_name
    return None


def resolve_model_meta(
    base_url: str,
    api_key: str | None = None,
    model: str | None = None,
    model_label: str | None = None,
) -> LmStudioModelMeta:
    """Fetch library metadata and resolve it for one configured model.

    Never raises; returns an empty meta (plus a stderr warning when the
    server was reachable but no entry matched) so benchmark runs proceed
    with config fallbacks either way.
    """
    if not is_local_server(base_url):
        return LmStudioModelMeta()

    models = fetch_models(derive_base_root(base_url), api_key=api_key)
    if not models:
        return LmStudioModelMeta()

    entry = match_model(models, model=model, model_label=model_label)
    if entry is None:
        available = ", ".join(str(entry.get("key")) for entry in models[:10]) or "(none)"
        print(
            "Warning: LM Studio listed models but none matched the configured "
            f"model ({model!r}/{model_label!r}). Available keys: {available}. "
            "Continuing without model size/quantization.",
            file=sys.stderr,
        )
        return LmStudioModelMeta()

    return parse_model_meta(entry)


def parse_model_meta(entry: dict[str, Any]) -> LmStudioModelMeta:
    """Normalize metadata from one LM Studio model entry."""
    quantization = entry.get("quantization")
    quantization_name = (
        str(quantization["name"]).strip() or None
        if isinstance(quantization, dict) and quantization.get("name")
        else None
    )
    size_bytes_raw = entry.get("size_bytes")
    try:
        size_bytes = int(size_bytes_raw) if size_bytes_raw is not None else None
    except (TypeError, ValueError):
        size_bytes = None
    params_string = (
        str(entry["params_string"]).strip() or None
        if entry.get("params_string")
        else None
    )
    return LmStudioModelMeta(
        size_bytes=size_bytes,
        quantization=quantization_name,
        params_string=params_string,
    )


def format_model_size(size_bytes: int | None) -> str:
    """Render a byte count as GB with one decimal (GiB-based), or 'n/a'."""
    if size_bytes is None:
        return "n/a"
    return f"{size_bytes / 2**30:.1f} GB"
