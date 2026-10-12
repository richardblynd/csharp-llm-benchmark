from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import subprocess
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
    callers can proceed without special-casing errors. The benchmark CLI asks
    for missing quantization/size; publisher and display name come from the API.
    """

    size_bytes: int | None = None
    quantization: str | None = None
    params_string: str | None = None
    publisher: str | None = None
    display_name: str | None = None


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
            f"{timeout_seconds}s ({url}). Continuing without model metadata.",
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
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(
            f"Warning: could not reach LM Studio metadata endpoint at {url} "
            f"({exc}). Continuing without model metadata.",
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


def _is_same_machine(hostname: str) -> bool:
    """Only let the local CLI supply metadata for this machine's server."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
        local_addresses = {
            info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None)
        }
        return bool(addresses) and all(
            ipaddress.ip_address(address).is_loopback or address in local_addresses
            for address in addresses
        )
    except (OSError, ValueError):
        return False


def fetch_loaded_models(base_url: str) -> list[dict[str, Any]]:
    """Read actual loaded instances using the optional local LM Studio CLI.

    Catalog REST endpoints can report the default variant even when another
    variant is loaded. Verify host and HTTP port before using local CLI data;
    never substitute this machine's models for a different server's models.
    """
    root = urlparse(derive_base_root(base_url))
    if root.scheme != "http" or root.path or not _is_same_machine(root.hostname or ""):
        return []
    executable = shutil.which("lms")
    if executable is None:
        return []
    try:
        def query(*args: str) -> Any:
            result = subprocess.run(
                [executable, *args], capture_output=True, text=True,
                encoding="utf-8", timeout=10, check=True,
            )
            return json.loads(result.stdout)

        status = query("server", "status", "--json")
        if (
            not isinstance(status, dict) or status.get("running") is not True
            or status.get("port") != (root.port or 80)
        ):
            return []
        loaded = query("ps", "--json")
        if isinstance(loaded, list):
            return [entry for entry in loaded if isinstance(entry, dict)]
    except (OSError, subprocess.SubprocessError, ValueError):
        print(
            "Warning: could not query loaded LM Studio instances with lms; "
            "only unambiguous catalog metadata will be used.", file=sys.stderr,
        )
    return []


def match_model(
    models: list[dict[str, Any]],
    model: str | None = None,
    model_label: str | None = None,
) -> dict[str, Any] | None:
    """Find the library entry for a model by key or display name.

    Try loaded instance ID, exact key/variant and casefolded key for each
    candidate, then casefolded display names. Candidates are tried in this
    order: `model` (the API id), then `model_label` (user-facing label).
    """
    candidates = [value for value in (model, model_label) if value]
    for candidate in candidates:
        by_instance = next(
            (entry for entry in models
             if any(instance.get("id") == candidate
                    for instance in (entry.get("loaded_instances") or [])
                    if isinstance(instance, dict))), None,
        )
        if by_instance is not None:
            return by_instance
        exact_key = next(
            (entry for entry in models if entry.get("key") == candidate), None
        )
        if exact_key is not None:
            return exact_key
        by_variant = next(
            (entry for entry in models if candidate in (entry.get("variants") or [])), None
        )
        if by_variant is not None:
            return by_variant
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
    """Resolve instance metadata, with an unambiguous library fallback.

    Never raises; returns an empty meta (plus a stderr warning when the
    server was reachable but no entry matched) so benchmark runs proceed
    and the CLI can ask for missing quantization and size.
    """
    if not is_local_server(base_url):
        return LmStudioModelMeta()

    models = fetch_models(derive_base_root(base_url), api_key=api_key)
    loaded_models = fetch_loaded_models(base_url)
    matches = [entry for entry in loaded_models if model and entry.get("identifier") == model]
    if not matches:
        matches = [entry for entry in loaded_models if model and entry.get("modelKey") == model]
    loaded = matches[0] if len(matches) == 1 else None
    entry = match_model(models, model=model, model_label=model_label)
    if loaded is not None:
        if entry is None:
            entry = match_model(models, model=loaded.get("modelKey"))
        # Identity fields may come from the catalog; variant fields must come
        # exclusively from the matched running instance, including when absent.
        resolved = dict(entry or {})
        resolved.pop("variants", None)
        resolved.update({
            "quantization": loaded.get("quantization"),
            "size_bytes": loaded.get("sizeBytes"),
        })
        for source, target in (("displayName", "display_name"),
                               ("publisher", "publisher"), ("paramsString", "params_string")):
            if loaded.get(source):
                resolved[target] = loaded[source]
        return parse_model_meta(resolved)
    if not models:
        return LmStudioModelMeta()
    if entry is None:
        available = ", ".join(str(entry.get("key")) for entry in models[:10]) or "(none)"
        print(
            "Warning: LM Studio listed models but none matched the configured "
            f"model ({model!r}/{model_label!r}). Available keys: {available}. "
            "Continuing without model metadata.",
            file=sys.stderr,
        )
        return LmStudioModelMeta()

    if len(entry.get("variants") or []) > 1:
        print(
            f"Warning: LM Studio model {model!r} has multiple variants, but its "
            "loaded instance could not be identified. Ignoring catalog quantization "
            "and size.", file=sys.stderr,
        )
    return parse_model_meta(entry)


def parse_model_meta(entry: dict[str, Any]) -> LmStudioModelMeta:
    """Normalize metadata, withholding variant fields for grouped catalog entries."""
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
    display_name = entry.get("display_name")
    if len(entry.get("variants") or []) > 1:
        quantization_name = None
        size_bytes = None
    return LmStudioModelMeta(
        size_bytes=size_bytes,
        quantization=quantization_name,
        params_string=params_string,
        publisher=format_publisher(entry.get("publisher")),
        display_name=(
            display_name.strip() or None if isinstance(display_name, str) else None
        ),
    )


def format_publisher(publisher: Any) -> str | None:
    """Render the API publisher for logs and results."""
    if not isinstance(publisher, str) or not publisher.strip():
        return None
    publisher = publisher.strip()
    aliases = {
        "lmstudio-community": "LM Studio Community",
        "prism-ml": "Prism ML",
    }
    return aliases.get(publisher.casefold(), publisher[0].upper() + publisher[1:])


def format_model_size(size_bytes: int | None) -> str:
    """Render a byte count as GB with one decimal (GiB-based), or 'n/a'."""
    if size_bytes is None:
        return "n/a"
    return f"{size_bytes / 2**30:.1f} GB"
