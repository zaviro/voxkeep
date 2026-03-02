#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../../../.." && pwd)"
BASE_URL="http://127.0.0.1:9880"
FIXTURE_DIR="$PROJECT_ROOT/tests/fixtures/audio/gptsovits"
REF_AUDIO=""
DEFAULT_PROMPT_TEXT="你好，这是默认参考提示词。"
PROMPT_TEXT="$DEFAULT_PROMPT_TEXT"
TEXT_LANG="zh"
PROMPT_LANG="zh"
GPTSOVITS_WORKSPACE="${HOME%/}/workspace/gptsovits"
CONTAINER_NAME="${GPTSOVITS_CONTAINER_NAME:-gptsovits-v2pro-plus}"
MODEL_IMAGE="breakstring/gpt-sovits:latest"
TTS_DEVICE="cuda"
START_SERVICE=0
START_API=1
FORCE=0
BOOTSTRAP_ASSETS=1

usage() {
  cat <<'USAGE'
Generate deterministic GPT-SoVITS audio fixtures for E2E tests.

Usage:
  generate_test_fixtures.sh [options]

Options:
  --project-root <path>          Repository root (default: auto-detected)
  --base-url <url>               GPT-SoVITS API base url (default: http://127.0.0.1:9880)
  --fixture-dir <path>           Fixture output directory
  --ref-audio <path>             Reference audio path (default: auto-detected)
  --prompt-text <text>           Prompt text matching reference audio
  --text-lang <lang>             Target text language (default: zh)
  --prompt-lang <lang>           Prompt language (default: zh)
  --gptsovits-workspace <path>   GPT-SoVITS workspace root (default: $HOME/workspace/gptsovits)
  --container-name <name>        Running GPT-SoVITS container (default: gptsovits-v2pro-plus)
  --model-image <image>          Image used to bootstrap default models
  --device <cpu|cuda>            Device for api.py (default: cuda)
  --start-service                Run docker compose up -d before generation
  --no-start-api                 Do not auto-start api.py inside running container
  --no-bootstrap-assets          Do not auto-bootstrap default reference/model assets
  --force                        Regenerate even if fixture already exists
  -h, --help                     Show help

Default bootstrap behavior:
  1) Ensure default models under <project>/models (auto-copy from --model-image when missing)
  2) Ensure reference audio <project>/inputs/default_reference.wav (auto-extract from zip when possible)
  3) Sync defaults into --gptsovits-workspace for mounted container runtime
USAGE
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1" >&2
    exit 1
  fi
}

is_model_file() {
  case "$1" in
    *.pth|*.pt|*.ckpt|*.safetensors|*.onnx) return 0 ;;
    *) return 1 ;;
  esac
}

has_model_file() {
  local root="$1"
  if [[ ! -d "$root" ]]; then
    return 1
  fi
  while IFS= read -r -d '' file; do
    if is_model_file "$file"; then
      return 0
    fi
  done < <(find "$root" -type f -print0)
  return 1
}

bootstrap_models_from_image() {
  local models_root="$PROJECT_ROOT/models"
  mkdir -p "$models_root"

  if has_model_file "$models_root"; then
    return
  fi

  require_cmd docker
  echo "Bootstrapping default models from image: $MODEL_IMAGE"

  docker run --rm \
    -v "$models_root:/out" \
    "$MODEL_IMAGE" \
    sh -lc '
      set -e
      src="/workspace/GPT_SoVITS/pretrained_models"
      cp -an "$src/chinese-hubert-base" /out/
      cp -an "$src/chinese-roberta-wwm-ext-large" /out/
      cp -an "$src/s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt" /out/
      cp -an "$src/s2G488k.pth" /out/
      cp -an "$src/s2D488k.pth" /out/
    '

  if ! has_model_file "$models_root"; then
    echo "Failed to bootstrap default models under $models_root" >&2
    exit 1
  fi
}

find_reference_zip() {
  local candidates=(
    "$PROJECT_ROOT/models/希儿.zip"
    "$GPTSOVITS_WORKSPACE/models/希儿.zip"
  )

  local c
  for c in "${candidates[@]}"; do
    if [[ -f "$c" ]]; then
      printf '%s\n' "$c"
      return 0
    fi
  done

  if [[ -d "$PROJECT_ROOT/models" ]]; then
    c="$(find "$PROJECT_ROOT/models" -maxdepth 1 -type f -name '*.zip' | head -n 1 || true)"
    if [[ -n "$c" ]]; then
      printf '%s\n' "$c"
      return 0
    fi
  fi

  if [[ -d "$GPTSOVITS_WORKSPACE/models" ]]; then
    c="$(find "$GPTSOVITS_WORKSPACE/models" -maxdepth 1 -type f -name '*.zip' | head -n 1 || true)"
    if [[ -n "$c" ]]; then
      printf '%s\n' "$c"
      return 0
    fi
  fi

  printf '\n'
  return 1
}

extract_default_reference_from_zip() {
  local zip_path="$1"
  local out_path="$PROJECT_ROOT/inputs/default_reference.wav"

  mkdir -p "$PROJECT_ROOT/inputs"

  local inferred_prompt
  inferred_prompt="$(python - "$zip_path" "$out_path" <<'PY'
import re
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])

with zipfile.ZipFile(zip_path) as zf:
    wav_names = [name for name in zf.namelist() if name.lower().endswith('.wav')]
    if not wav_names:
        raise SystemExit('zip has no wav reference audio')

    selected = wav_names[0]
    data = zf.read(selected)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)

    stem = Path(selected).stem
    stem = re.sub(r'^【[^】]+】', '', stem)
    stem = stem.strip() or '你好，这是默认参考提示词。'
    print(stem)
PY
)"

  if [[ -n "$inferred_prompt" && "$PROMPT_TEXT" == "$DEFAULT_PROMPT_TEXT" ]]; then
    PROMPT_TEXT="$inferred_prompt"
  fi
}

sync_assets_to_gptsovits_workspace() {
  if [[ ! -d "$GPTSOVITS_WORKSPACE" ]]; then
    return
  fi

  mkdir -p "$GPTSOVITS_WORKSPACE/inputs" "$GPTSOVITS_WORKSPACE/models"

  if [[ -f "$PROJECT_ROOT/inputs/default_reference.wav" ]]; then
    cp -f "$PROJECT_ROOT/inputs/default_reference.wav" "$GPTSOVITS_WORKSPACE/inputs/default_reference.wav"
  fi

  local name
  for name in \
    chinese-hubert-base \
    chinese-roberta-wwm-ext-large \
    s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt \
    s2G488k.pth \
    s2D488k.pth \
    希儿.zip; do
    if [[ -e "$PROJECT_ROOT/models/$name" && ! -e "$GPTSOVITS_WORKSPACE/models/$name" ]]; then
      cp -a "$PROJECT_ROOT/models/$name" "$GPTSOVITS_WORKSPACE/models/$name"
    fi
  done
}

resolve_default_ref_audio() {
  local candidate
  for candidate in \
    "$PROJECT_ROOT/inputs/default_reference.wav" \
    "$PROJECT_ROOT/inputs/reference.wav" \
    "$GPTSOVITS_WORKSPACE/inputs/default_reference.wav" \
    "$GPTSOVITS_WORKSPACE/inputs/reference.wav"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  printf '\n'
  return 1
}

assert_default_models_exist() {
  if ! has_model_file "$PROJECT_ROOT/models"; then
    echo "No default model file found under $PROJECT_ROOT/models" >&2
    echo "Expected extensions: .pth/.pt/.ckpt/.safetensors/.onnx" >&2
    exit 1
  fi
}

probe_api_endpoint() {
  local endpoint="$1"
  local tmp_file
  tmp_file="$(mktemp)"
  local http_code

  http_code="$(
    curl -sS \
      -X POST "${BASE_URL%/}${endpoint}" \
      -H 'content-type: application/json' \
      --data '{}' \
      -o "$tmp_file" \
      -w '%{http_code}' || true
  )"
  rm -f "$tmp_file"

  case "$http_code" in
    200|400|422|500)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

check_api_reachable() {
  probe_api_endpoint "/tts" || probe_api_endpoint "/"
}

extract_api_port() {
  local port
  port="$(printf '%s' "$BASE_URL" | sed -nE 's#^https?://[^:/]+:([0-9]+).*$#\1#p')"
  if [[ -z "$port" ]]; then
    port="9880"
  fi
  printf '%s\n' "$port"
}

start_api_in_container() {
  require_cmd docker

  if ! docker ps --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    echo "Container not running: $CONTAINER_NAME" >&2
    return 1
  fi

  local api_port
  api_port="$(extract_api_port)"
  local workspace_starter="$GPTSOVITS_WORKSPACE/scripts/start_api_cuda.sh"

  if [[ -x "$workspace_starter" ]]; then
    CONTAINER_NAME="$CONTAINER_NAME" \
    API_HOST="0.0.0.0" \
    API_PORT="$api_port" \
    API_DEVICE="$TTS_DEVICE" \
    REF_AUDIO="/workspace/reference/default_reference.wav" \
    PROMPT_TEXT="$PROMPT_TEXT" \
    PROMPT_LANG="$PROMPT_LANG" \
    "$workspace_starter" >/dev/null
  else
    docker exec \
      -e ASR_API_PORT="$api_port" \
      -e ASR_PROMPT_TEXT="$PROMPT_TEXT" \
      -e ASR_PROMPT_LANG="$PROMPT_LANG" \
      -e ASR_TTS_DEVICE="$TTS_DEVICE" \
      "$CONTAINER_NAME" \
      sh -lc '
        set -e
        pkill -f "^python .*api.py" >/dev/null 2>&1 || true
        cd /workspace
        nohup python api.py \
          -a 0.0.0.0 \
          -p "$ASR_API_PORT" \
          -d "$ASR_TTS_DEVICE" \
          -dr /workspace/reference/default_reference.wav \
          -dt "$ASR_PROMPT_TEXT" \
          -dl "$ASR_PROMPT_LANG" \
          > /tmp/gptsovits-api.log 2>&1 &
      '
  fi

  local attempt
  for attempt in $(seq 1 40); do
    if check_api_reachable; then
      return 0
    fi
    sleep 1
  done

  echo "api.py did not become reachable at ${BASE_URL%/}" >&2
  docker exec "$CONTAINER_NAME" sh -lc 'tail -n 80 /tmp/gptsovits-api.log 2>/dev/null || true' >&2
  return 1
}

normalize_fixture_wav() {
  local output="$1"
  local tmp_output="${output}.norm.wav"

  ffmpeg -y -loglevel error -i "$output" -ar 16000 -ac 1 "$tmp_output"
  mv "$tmp_output" "$output"
}

generate_one() {
  local output="$1"
  local text="$2"

  if [[ -f "$output" && "$FORCE" -ne 1 ]]; then
    echo "Skip existing fixture: $output"
    return
  fi

  "$SCRIPT_DIR/tts_request.sh" \
    --project-root "$PROJECT_ROOT" \
    --gptsovits-workspace "$GPTSOVITS_WORKSPACE" \
    --base-url "$BASE_URL" \
    --text "$text" \
    --text-lang "$TEXT_LANG" \
    --ref-audio "$REF_AUDIO" \
    --prompt-lang "$PROMPT_LANG" \
    --prompt-text "$PROMPT_TEXT" \
    --output "$output"

  normalize_fixture_wav "$output"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --fixture-dir)
      FIXTURE_DIR="${2:-}"
      shift 2
      ;;
    --ref-audio)
      REF_AUDIO="${2:-}"
      shift 2
      ;;
    --prompt-text)
      PROMPT_TEXT="${2:-}"
      shift 2
      ;;
    --text-lang)
      TEXT_LANG="${2:-}"
      shift 2
      ;;
    --prompt-lang)
      PROMPT_LANG="${2:-}"
      shift 2
      ;;
    --gptsovits-workspace)
      GPTSOVITS_WORKSPACE="${2:-}"
      shift 2
      ;;
    --container-name)
      CONTAINER_NAME="${2:-}"
      shift 2
      ;;
    --model-image)
      MODEL_IMAGE="${2:-}"
      shift 2
      ;;
    --device)
      TTS_DEVICE="${2:-}"
      shift 2
      ;;
    --start-service)
      START_SERVICE=1
      shift 1
      ;;
    --no-start-api)
      START_API=0
      shift 1
      ;;
    --no-bootstrap-assets)
      BOOTSTRAP_ASSETS=0
      shift 1
      ;;
    --force)
      FORCE=1
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_cmd curl
require_cmd jq
require_cmd ffmpeg

if [[ "$TTS_DEVICE" != "cpu" && "$TTS_DEVICE" != "cuda" ]]; then
  echo "--device must be one of: cpu, cuda" >&2
  exit 1
fi

mkdir -p "$PROJECT_ROOT/inputs" "$PROJECT_ROOT/models"

if [[ "$BOOTSTRAP_ASSETS" -eq 1 ]]; then
  bootstrap_models_from_image

  if [[ ! -f "$PROJECT_ROOT/inputs/default_reference.wav" && ! -f "$PROJECT_ROOT/inputs/reference.wav" ]]; then
    zip_path="$(find_reference_zip || true)"
    if [[ -n "$zip_path" ]]; then
      echo "Extracting default reference audio from zip: $zip_path"
      extract_default_reference_from_zip "$zip_path"
    fi
  fi

  sync_assets_to_gptsovits_workspace
fi

if [[ "$START_SERVICE" -eq 1 ]]; then
  require_cmd docker
  if [[ -f "$GPTSOVITS_WORKSPACE/docker-compose.yml" ]]; then
    (cd "$GPTSOVITS_WORKSPACE" && docker compose up -d >/dev/null)
  else
    echo "docker-compose.yml not found under $GPTSOVITS_WORKSPACE" >&2
    exit 1
  fi
fi

if [[ -z "$REF_AUDIO" ]]; then
  REF_AUDIO="$(resolve_default_ref_audio || true)"
fi

if [[ -z "$REF_AUDIO" ]]; then
  echo "Missing default reference audio. Expected one of:" >&2
  echo "  - $PROJECT_ROOT/inputs/default_reference.wav" >&2
  echo "  - $PROJECT_ROOT/inputs/reference.wav" >&2
  echo "  - $GPTSOVITS_WORKSPACE/inputs/default_reference.wav" >&2
  echo "  - $GPTSOVITS_WORKSPACE/inputs/reference.wav" >&2
  exit 1
fi

if [[ "$REF_AUDIO" != /workspace/* ]]; then
  if [[ "$REF_AUDIO" != /* ]]; then
    REF_AUDIO="${PROJECT_ROOT%/}/$REF_AUDIO"
  fi
  if [[ ! -f "$REF_AUDIO" ]]; then
    echo "Reference audio not found: $REF_AUDIO" >&2
    exit 1
  fi
fi

assert_default_models_exist

if [[ "$START_API" -eq 1 ]]; then
  echo "Starting/restarting api.py in container: $CONTAINER_NAME (device=$TTS_DEVICE)"
  start_api_in_container
elif ! check_api_reachable; then
  echo "GPT-SoVITS API unreachable at ${BASE_URL%/} and auto-start disabled" >&2
  exit 1
fi

mkdir -p "$FIXTURE_DIR"

ALEXA_FIXTURE="$FIXTURE_DIR/alexa_inject_text_zh.wav"
HEY_JARVIS_FIXTURE="$FIXTURE_DIR/hey_jarvis_openclaw_zh.wav"

ALEXA_TEXT="你好，流水线端到端测试"
HEY_JARVIS_TEXT="请忽略其他内容，只回复：你好这里是openclaw"

generate_one "$ALEXA_FIXTURE" "$ALEXA_TEXT"
generate_one "$HEY_JARVIS_FIXTURE" "$HEY_JARVIS_TEXT"

echo "Generated fixtures:"
ls -lh "$ALEXA_FIXTURE" "$HEY_JARVIS_FIXTURE"
