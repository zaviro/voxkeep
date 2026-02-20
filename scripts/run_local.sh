#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-config/config.yaml}"
UV_PYTHON="${ASR_OL_UV_PYTHON:-3.11}"
MANAGE_FUNASR="${ASR_OL_MANAGE_FUNASR:-1}"
FUNASR_SESSION="${ASR_OL_FUNASR_SESSION:-funasr_local}"
FUNASR_DIR="${ASR_OL_FUNASR_DIR:-/home/user/workspace/FunASR/runtime/python/websocket}"
FUNASR_PYTHON="${ASR_OL_FUNASR_PYTHON:-/home/user/workspace/FunASR/.venv311/bin/python}"
FUNASR_HOST="${FUNASR_HOST:-127.0.0.1}"
FUNASR_PORT="${FUNASR_PORT:-10096}"
FUNASR_NGPU="${ASR_OL_FUNASR_NGPU:-auto}"
FUNASR_DEVICE="${ASR_OL_FUNASR_DEVICE:-auto}"
FUNASR_NCPU="${ASR_OL_FUNASR_NCPU:-8}"
FUNASR_START_TIMEOUT_S="${ASR_OL_FUNASR_START_TIMEOUT_S:-30}"

STARTED_FUNASR=0
RESOLVED_FUNASR_NGPU="$FUNASR_NGPU"
RESOLVED_FUNASR_DEVICE="$FUNASR_DEVICE"

run_python() {
  if command -v uv >/dev/null 2>&1; then
    uv run --python "$UV_PYTHON" python "$@"
  elif [[ -x ".venv/bin/python" ]]; then
    .venv/bin/python "$@"
  else
    python3 "$@"
  fi
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ "$STARTED_FUNASR" == "1" ]]; then
    tmux kill-session -t "$FUNASR_SESSION" 2>/dev/null || true
  fi
  exit "$exit_code"
}

wait_funasr_ready() {
  local waited=0
  while (( waited < FUNASR_START_TIMEOUT_S )); do
    if run_python - <<PY
import socket
import sys

s = socket.socket()
s.settimeout(1.0)
try:
    s.connect(("${FUNASR_HOST}", int("${FUNASR_PORT}")))
except Exception:
    sys.exit(1)
else:
    s.close()
    sys.exit(0)
PY
    then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

resolve_funasr_runtime() {
  local cuda_available=0
  local cuda_count=0
  local detect_output=""

  if [[ "$FUNASR_DEVICE" == "auto" || "$FUNASR_NGPU" == "auto" ]]; then
    detect_output="$("$FUNASR_PYTHON" - <<'PY' 2>/dev/null || true
try:
    import torch
except Exception:
    print("0 0")
else:
    has_cuda = int(bool(torch.cuda.is_available()))
    device_count = int(torch.cuda.device_count()) if has_cuda else 0
    print(f"{has_cuda} {device_count}")
PY
)"
    if [[ "$detect_output" =~ ^([0-9]+)[[:space:]]+([0-9]+)$ ]]; then
      cuda_available="${BASH_REMATCH[1]}"
      cuda_count="${BASH_REMATCH[2]}"
    fi
  fi

  RESOLVED_FUNASR_NGPU="$FUNASR_NGPU"
  RESOLVED_FUNASR_DEVICE="$FUNASR_DEVICE"

  if [[ "$RESOLVED_FUNASR_DEVICE" == "auto" ]]; then
    if [[ "$RESOLVED_FUNASR_NGPU" != "auto" ]]; then
      if [[ "$RESOLVED_FUNASR_NGPU" == "0" ]]; then
        RESOLVED_FUNASR_DEVICE="cpu"
      else
        RESOLVED_FUNASR_DEVICE="cuda"
      fi
    elif (( cuda_available == 1 && cuda_count > 0 )); then
      RESOLVED_FUNASR_DEVICE="cuda"
    else
      RESOLVED_FUNASR_DEVICE="cpu"
    fi
  fi

  if [[ "$RESOLVED_FUNASR_NGPU" == "auto" ]]; then
    if [[ "$RESOLVED_FUNASR_DEVICE" == "cuda" ]]; then
      RESOLVED_FUNASR_NGPU="1"
    else
      RESOLVED_FUNASR_NGPU="0"
    fi
  fi

  if [[ "$RESOLVED_FUNASR_DEVICE" == "cpu" ]]; then
    RESOLVED_FUNASR_NGPU="0"
  fi

  if [[ "$RESOLVED_FUNASR_DEVICE" == "cuda" && "$RESOLVED_FUNASR_NGPU" == "0" ]]; then
    echo "Invalid FunASR runtime config: device=cuda with ngpu=0" >&2
    return 1
  fi
}

start_funasr() {
  if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux is required when ASR_OL_MANAGE_FUNASR=1" >&2
    return 1
  fi
  if [[ ! -x "$FUNASR_PYTHON" ]]; then
    echo "FunASR python not executable: $FUNASR_PYTHON" >&2
    return 1
  fi

  resolve_funasr_runtime
  echo "Starting FunASR: host=$FUNASR_HOST port=$FUNASR_PORT device=$RESOLVED_FUNASR_DEVICE ngpu=$RESOLVED_FUNASR_NGPU ncpu=$FUNASR_NCPU"

  tmux kill-session -t "$FUNASR_SESSION" 2>/dev/null || true

  local launch_cmd
  printf -v launch_cmd \
    "cd %q && exec %q -u funasr_wss_server.py --host %q --port %q --ngpu %q --device %q --ncpu %q --certfile '' --keyfile ''" \
    "$FUNASR_DIR" "$FUNASR_PYTHON" "$FUNASR_HOST" "$FUNASR_PORT" "$RESOLVED_FUNASR_NGPU" "$RESOLVED_FUNASR_DEVICE" "$FUNASR_NCPU"
  tmux new-session -d -s "$FUNASR_SESSION" "$launch_cmd"
  STARTED_FUNASR=1

  if ! wait_funasr_ready; then
    echo "FunASR failed to become ready within ${FUNASR_START_TIMEOUT_S}s" >&2
    tmux capture-pane -pt "$FUNASR_SESSION" -S -80 || true
    return 1
  fi
}

trap cleanup EXIT INT TERM

if [[ "$MANAGE_FUNASR" == "1" ]]; then
  start_funasr
fi

if command -v uv >/dev/null 2>&1; then
  uv run --python "$UV_PYTHON" python -m asr_ol --config "$CONFIG_PATH"
else
  python3 -m asr_ol --config "$CONFIG_PATH"
fi
