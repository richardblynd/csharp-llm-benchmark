#!/usr/bin/env python3
"""Backfill kv_cache_quantization into existing summary.json files.

Idempotent: skips any summary that already has the field set.

Rule: if llm.base_url contains "api.openai.com" → GPT cloud → null.
      Otherwise → local run → "Q4".
"""

import json
from pathlib import Path


def main() -> None:
    results_dir = Path("results")
    if not results_dir.is_dir():
        print(f"No results directory found at {results_dir} — nothing to backfill.")
        return

    migrated = 0

    for run_dir in sorted(d for d in results_dir.iterdir() if d.is_dir()):
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue

        data = json.loads(summary_path.read_text(encoding="utf-8"))

        # Idempotent: skip if key already exists (even if null)
        if "kv_cache_quantization" in data:
            continue

        base_url = str(data.get("llm", {}).get("base_url", ""))
        is_gpt_cloud = "api.openai.com" in base_url

        new_value = None if is_gpt_cloud else "Q4"
        data["kv_cache_quantization"] = new_value
        data.setdefault("llm", {})["kv_cache_quantization"] = new_value

        summary_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        migrated += 1
        print(f"  Backfilled {run_dir.name} → kv_cache_quantization={new_value}")

    print(f"\nDone. Migrated {migrated} run(s).")


if __name__ == "__main__":
    main()
