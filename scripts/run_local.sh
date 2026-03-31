#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-config/config.yaml}"
UV_PYTHON="${VOXKEEP_UV_PYTHON:-3.11}"
MANAGE_FUNASR="${VOXKEEP_MANAGE_FUNASR:-1}"
FUNASR_MANAGER="${VOXKEEP_FUNASR_MANAGER:-docker}"
FUNASR_COMPOSE_FILE="${VOXKEEP_FUNASR_COMPOSE_FILE:-docker-compose.yml}"
FUNASR_DOCKER_SERVICE="${VOXKEEP_FUNASR_DOCKER_SERVICE:-funasr}"
FUNASR_STOP_ON_EXIT="${VOXKEEP_FUNASR_STOP_ON_EXIT:-1}"
FUNASR_HOST="${VOXKEEP_FUNASR_HOST:-${FUNASR_HOST:-127.0.0.1}}"
FUNASR_PORT="${VOXKEEP_FUNASR_PORT:-${FUNASR_PORT:-10096}}"
FUNASR_START_TIMEOUT_S="${VOXKEEP_FUNASR_START_TIMEOUT_S:-30}"

STARTED_FUNASR=0

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
  if [[ "$STARTED_FUNASR" == "1" && "$FUNASR_STOP_ON_EXIT" == "1" ]]; then
    compose_cmd stop "$FUNASR_DOCKER_SERVICE" >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}

compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose -f "$FUNASR_COMPOSE_FILE" "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f "$FUNASR_COMPOSE_FILE" "$@"
    return
  fi
  echo "docker compose command not found" >&2
  return 1
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

start_funasr_docker() {
  if [[ ! -f "$FUNASR_COMPOSE_FILE" ]]; then
    echo "compose file not found: $FUNASR_COMPOSE_FILE" >&2
    return 1
  fi

  if ! compose_cmd config --services | grep -Fxq "$FUNASR_DOCKER_SERVICE"; then
    echo "service '$FUNASR_DOCKER_SERVICE' not found in $FUNASR_COMPOSE_FILE" >&2
    return 1
  fi

  echo "Starting FunASR service via compose: service=$FUNASR_DOCKER_SERVICE host=$FUNASR_HOST port=$FUNASR_PORT"
  compose_cmd up -d "$FUNASR_DOCKER_SERVICE"
  STARTED_FUNASR=1
}

trap cleanup EXIT INT TERM

if [[ "$MANAGE_FUNASR" == "1" ]]; then
  case "$FUNASR_MANAGER" in
    docker)
      start_funasr_docker
      ;;
    *)
      echo "unsupported VOXKEEP_FUNASR_MANAGER='$FUNASR_MANAGER' (supported: docker)" >&2
      exit 1
      ;;
  esac
fi

if ! wait_funasr_ready; then
  echo "FunASR failed to become ready within ${FUNASR_START_TIMEOUT_S}s at ${FUNASR_HOST}:${FUNASR_PORT}" >&2
  echo "Hint: check service logs: docker compose -f ${FUNASR_COMPOSE_FILE} logs --tail=200 ${FUNASR_DOCKER_SERVICE}" >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  uv run --python "$UV_PYTHON" python -m voxkeep --config "$CONFIG_PATH"
else
  python3 -m voxkeep --config "$CONFIG_PATH"
fi
