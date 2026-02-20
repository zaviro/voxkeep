#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-config/config.yaml}"
UV_PYTHON="${ASR_OL_UV_PYTHON:-3.11}"

if command -v uv >/dev/null 2>&1; then
  uv run --python "$UV_PYTHON" python -m asr_ol --config "$CONFIG_PATH"
else
  python3 -m asr_ol --config "$CONFIG_PATH"
fi
