#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${VOXKEEP_STATE_DIR:-$HOME/.local/state/voxkeep}"
PID_FILE="$STATE_DIR/qwen_vllm.pid"
SERVICE_DIR="${VOXKEEP_QWEN_SERVICE_DIR:-$HOME/.local/share/voxkeep/qwen3-asr-service}"
VENV_DIR="${VOXKEEP_QWEN_VENV_DIR:-$SERVICE_DIR/.venv}"

stop_pid() {
  local pid="$1"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" || true
    sleep 2
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" || true
    fi
    echo "qwen vllm stopped pid=$pid"
    return 0
  fi
  return 1
}

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if [[ -n "$pid" ]] && stop_pid "$pid"; then
    rm -f "$PID_FILE"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

mapfile -t pids < <(pgrep -f "$VENV_DIR/bin/vllm serve" || true)
if [[ "${#pids[@]}" -eq 0 ]]; then
  echo "qwen vllm is not running"
  exit 0
fi

stopped=0
for pid in "${pids[@]}"; do
  if stop_pid "$pid"; then
    stopped=1
  fi
done

rm -f "$PID_FILE"
if [[ "$stopped" -eq 0 ]]; then
  echo "qwen vllm matched processes were already gone"
fi
