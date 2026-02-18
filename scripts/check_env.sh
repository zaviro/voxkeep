#!/usr/bin/env bash
set -euo pipefail

PASS=0
FAIL=0

run_python() {
  if command -v uv >/dev/null 2>&1; then
    uv run python "$@"
  elif [[ -x ".venv/bin/python" ]]; then
    .venv/bin/python "$@"
  else
    python3 "$@"
  fi
}

mark_pass() {
  local name="$1"
  echo "[PASS] $name"
  PASS=$((PASS + 1))
}

mark_fail() {
  local name="$1"
  echo "[FAIL] $name"
  FAIL=$((FAIL + 1))
}

echo "== Session type =="
echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-}"
if [[ -n "${XDG_SESSION_TYPE:-}" ]]; then
  mark_pass "Session type"
else
  mark_fail "Session type"
fi
echo

echo "== Audio sources =="
if pactl list short sources; then
  mark_pass "Audio sources"
else
  mark_fail "Audio sources"
fi
DEFAULT_SOURCE="$(pactl info | awk -F': ' '/Default Source/ {print $2}')"
echo "Default Source: ${DEFAULT_SOURCE:-<none>}"
if [[ -z "${DEFAULT_SOURCE:-}" ]]; then
  mark_fail "Default source present"
elif [[ "${DEFAULT_SOURCE}" == *".monitor"* ]]; then
  mark_fail "Default source is physical microphone"
  echo "Hint: switch default source to a real input device with pavucontrol or pactl."
else
  mark_pass "Default source is physical microphone"
fi
echo

echo "== sounddevice import =="
if run_python -c 'import sounddevice; print("sounddevice ok")'; then
  mark_pass "sounddevice import"
else
  mark_fail "sounddevice import"
fi
echo

echo "== wake/vad runtime libs =="
if run_python -c 'import openwakeword, silero_vad; print("openwakeword + silero_vad ok")'; then
  mark_pass "wake/vad runtime libs"
else
  mark_fail "wake/vad runtime libs"
  echo "Hint: on Python 3.12, openwakeword may fail because tflite-runtime wheel is missing."
  echo "Hint: use uv Python 3.11 profile for full wake/vad stack:"
  echo "  make sync-ai && make check-ai"
fi
echo

echo "== FunASR TCP reachable =="
FUNASR_HOST="${FUNASR_HOST:-127.0.0.1}"
FUNASR_PORT="${FUNASR_PORT:-10096}"
if run_python - <<PY
import socket

host = "${FUNASR_HOST}"
port = int("${FUNASR_PORT}")
s = socket.socket()
s.settimeout(1.5)
s.connect((host, port))
print(f"funasr ok {host}:{port}")
s.close()
PY
then
  mark_pass "FunASR TCP reachable"
else
  mark_fail "FunASR TCP reachable"
fi
echo

if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  echo "== ydotool tools =="
  if command -v ydotool >/dev/null && command -v ydotoold >/dev/null; then
    mark_pass "ydotool tools"
  else
    mark_fail "ydotool tools"
  fi
else
  echo "== xdotool tool =="
  if command -v xdotool >/dev/null; then
    mark_pass "xdotool tool"
  else
    mark_fail "xdotool tool"
  fi
fi
echo

echo "Summary: PASS=$PASS FAIL=$FAIL"
if [[ "$FAIL" -gt 0 ]]; then
  echo "Some checks failed. Fix missing dependencies/permissions before runtime test."
  exit 1
fi
