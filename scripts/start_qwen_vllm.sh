#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-config/config.yaml}"
STATE_DIR="${VOXKEEP_STATE_DIR:-$HOME/.local/state/voxkeep}"
SERVICE_DIR="${VOXKEEP_QWEN_SERVICE_DIR:-$HOME/.local/share/voxkeep/qwen3-asr-service}"
VENV_DIR="${VOXKEEP_QWEN_VENV_DIR:-$SERVICE_DIR/.venv}"
PID_FILE="$STATE_DIR/qwen_vllm.pid"
LOG_FILE="$STATE_DIR/qwen_vllm.log"
HF_HOME_DIR="${HF_HOME:-$HOME/.local/share/voxkeep/huggingface}"
PROXY_URL="${VOXKEEP_QWEN_PROXY_URL:-socks5h://127.0.0.1:7897}"
STARTUP_TIMEOUT_S="${VOXKEEP_QWEN_STARTUP_TIMEOUT_S:-240}"
LOCAL_MODEL_ROOT="${VOXKEEP_QWEN_LOCAL_MODEL_ROOT:-$HOME/.local/share/voxkeep/models}"

mkdir -p "$STATE_DIR"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "qwen venv not found: $VENV_DIR" >&2
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE")"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
    echo "qwen vllm already running with pid=$existing_pid" >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

read_config() {
  PYTHONPATH="$PWD/src" "$VENV_DIR/bin/python" - <<'PY' "$CONFIG_PATH"
from pathlib import Path
import sys

from voxkeep.shared.config import load_config

cfg = load_config(Path(sys.argv[1]))
print(cfg.asr_external_host)
print(cfg.asr_external_port)
print(cfg.asr_qwen_model)
print("1" if cfg.asr_qwen_realtime else "0")
print(cfg.asr_qwen_gpu_memory_utilization)
print(cfg.asr_qwen_max_model_len)
PY
}

mapfile -t CFG_VALUES < <(cd "$(dirname "$0")/.." && read_config)

HOST="${CFG_VALUES[0]}"
PORT="${CFG_VALUES[1]}"
MODEL="${CFG_VALUES[2]}"
REALTIME_ENABLED="${CFG_VALUES[3]}"
GPU_MEMORY_UTILIZATION="${CFG_VALUES[4]}"
MAX_MODEL_LEN="${CFG_VALUES[5]}"
MODEL_SOURCE="$MODEL"
SERVED_MODEL_NAME=""

if [[ "$MODEL" == */* ]]; then
  local_candidate="$LOCAL_MODEL_ROOT/${MODEL%%/*}/${MODEL##*/}"
  if [[ -e "$local_candidate" ]]; then
    MODEL_SOURCE="$local_candidate"
    SERVED_MODEL_NAME="$MODEL"
  fi
fi

CMD=(
  "$VENV_DIR/bin/vllm"
  serve
  "$MODEL_SOURCE"
  --host "$HOST"
  --port "$PORT"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
)

if [[ -n "$SERVED_MODEL_NAME" ]]; then
  CMD+=(--served-model-name "$SERVED_MODEL_NAME")
fi

if [[ -n "$MAX_MODEL_LEN" ]] && [[ "$MAX_MODEL_LEN" != "0" ]]; then
  CMD+=(--max-model-len "$MAX_MODEL_LEN")
fi

if [[ "$REALTIME_ENABLED" == "1" ]]; then
  CMD+=(--hf-overrides '{"architectures":["Qwen3ASRRealtimeGeneration"]}')
fi

(
  export HF_HOME="$HF_HOME_DIR"
  export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
  export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
  export ALL_PROXY="${ALL_PROXY:-$PROXY_URL}"
  export HTTPS_PROXY="${HTTPS_PROXY:-$PROXY_URL}"
  export HTTP_PROXY="${HTTP_PROXY:-$PROXY_URL}"
  cd "$SERVICE_DIR"
  nohup setsid "${CMD[@]}" >>"$LOG_FILE" 2>&1 </dev/null &
  echo $! >"$PID_FILE"
)

deadline=$((SECONDS + STARTUP_TIMEOUT_S))
ready_url="http://$HOST:$PORT/v1/models"

while (( SECONDS < deadline )); do
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "qwen vllm exited during startup; inspect $LOG_FILE" >&2
    rm -f "$PID_FILE"
    exit 1
  fi

  if curl -fsS "$ready_url" >/dev/null 2>&1; then
    echo "qwen vllm started pid=$pid host=$HOST port=$PORT model=$MODEL realtime=$REALTIME_ENABLED"
    exit 0
  fi

  sleep 2
done

echo "qwen vllm did not become ready within ${STARTUP_TIMEOUT_S}s; inspect $LOG_FILE" >&2
tail -n 40 "$LOG_FILE" >&2 || true
exit 1
