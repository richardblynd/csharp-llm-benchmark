#!/usr/bin/env bash
set -euo pipefail

CONFIG="${1:-config.yaml}"
if [[ $# -gt 0 ]]; then
  shift
fi

python -m benchmark.cli run --config "$CONFIG" --difficulty hard "$@"
