#!/usr/bin/env python3
"""Backfill model_size_bytes/params_string into existing summary.json files.

Values come from a running LM Studio server (GET /api/v1/models), so the
models must still be present in its library for a match to succeed. Runs
whose models were removed stay untouched and render as 'n/a'.

Idempotent: skips any summary that already has model_size_bytes set.
Cloud/remote runs (non-loopback base_url) are never touched.
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmark.lmstudio_meta import (  # noqa: E402
    derive_base_root,
    format_model_size,
    is_local_server,
    match_model,
    fetch_models,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill model_size_bytes/params_string into existing "
            "summary.json files from a running LM Studio server."
        )
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing benchmark run folders. Defaults to ./results.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "LM Studio server URL (e.g. http://localhost:1234). When omitted, "
            "each run's own llm.base_url is used."
        ),
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Optional API key sent as Bearer token to the LM Studio server.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be backfilled without writing any file.",
    )
    args = parser.parse_args()

    results_dir: Path = args.results_dir
    if not results_dir.is_dir():
        print(f"No results directory found at {results_dir} — nothing to backfill.")
        return

    # Fetch each distinct server root once (usually just one).
    models_by_root: dict[str, list[dict]] = {}
    migrated = 0
    skipped = 0

    for run_dir in sorted(d for d in results_dir.iterdir() if d.is_dir()):
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue

        data = json.loads(summary_path.read_text(encoding="utf-8"))

        # Idempotent: skip if key already exists (even if null)
        if "model_size_bytes" in data:
            skipped += 1
            continue

        llm_payload = data.get("llm", {}) or {}
        base_url = str(llm_payload.get("base_url", ""))
        root = derive_base_root(args.base_url or base_url)
        if not is_local_server(root):
            print(f"  Skipped {run_dir.name} — remote/cloud run ({base_url}).")
            skipped += 1
            continue

        models = models_by_root.get(root)
        if models is None:
            models = fetch_models(root, api_key=args.api_key)
            models_by_root[root] = models
        if not models:
            print(f"  Skipped {run_dir.name} — LM Studio metadata unavailable.")
            skipped += 1
            continue

        entry = match_model(
            models,
            model=data.get("model"),
            model_label=data.get("modelLabel") or data.get("model_label"),
        )
        if entry is None:
            print(
                f"  Skipped {run_dir.name} — no library match for "
                f"{data.get('model')!r}/{data.get('modelLabel')!r}."
            )
            skipped += 1
            continue

        size_raw = entry.get("size_bytes")
        try:
            size_bytes = int(size_raw) if size_raw is not None else None
        except (TypeError, ValueError):
            size_bytes = None
        params_string = (
            str(entry["params_string"]).strip() or None
            if entry.get("params_string")
            else None
        )

        prefix = "[dry-run] " if args.dry_run else ""
        if size_bytes is not None:
            print(
                f"  {prefix}Backfilled {run_dir.name}: model_size_bytes="
                f"{size_bytes} ({format_model_size(size_bytes)}), "
                f"params_string={params_string!r}"
            )
        else:
            print(f"  Skipped {run_dir.name} — matched entry has no size.")
            skipped += 1
            continue

        if not args.dry_run:
            data["model_size_bytes"] = size_bytes
            data["params_string"] = params_string
            llm_section = data.setdefault("llm", {})
            llm_section["model_size_bytes"] = size_bytes
            llm_section["params_string"] = params_string
            summary_path.write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        migrated += 1

    verb = "Would migrate" if args.dry_run else "Migrated"
    print(f"\nDone. {verb} {migrated} run(s), skipped {skipped}.")


if __name__ == "__main__":
    main()
