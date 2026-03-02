#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:9880"
PROJECT_ROOT="$(pwd)"
GPTSOVITS_WORKSPACE="${HOME%/}/workspace/gptsovits"
TEXT=""
TEXT_LANG=""
REF_AUDIO=""
PROMPT_TEXT=""
PROMPT_LANG=""
TEXT_SPLIT_METHOD="cut5"
BATCH_SIZE=1
MEDIA_TYPE="wav"
OUTPUT=""
START_SERVICE=0

usage() {
  cat <<'USAGE'
Run GPT-SoVITS TTS request via HTTP API and save output audio.

Usage:
  tts_request.sh \
    --text "<text>" \
    --text-lang <lang> \
    --ref-audio <path> \
    --prompt-lang <lang> \
    --prompt-text "<text>" \
    [--output outputs/result.wav] \
    [--base-url http://127.0.0.1:9880] \
    [--project-root /path/to/repo] \
    [--gptsovits-workspace /path/to/gptsovits] \
    [--text-split-method cut5] \
    [--batch-size 1] \
    [--media-type wav] \
    [--start-service]

Notes:
  - Supports API v2 endpoint POST /tts (preferred).
  - Falls back to legacy API v1 endpoint POST / when /tts is unavailable.
USAGE
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1" >&2
    exit 1
  fi
}

resolve_local_path() {
  local input="$1"
  if [[ "$input" == /* ]]; then
    printf '%s\n' "$input"
  else
    printf '%s/%s\n' "${PROJECT_ROOT%/}" "$input"
  fi
}

map_ref_audio_path() {
  local input="$1"
  local candidate="$input"

  if [[ "$candidate" == /workspace/* ]]; then
    printf '%s\n' "$candidate"
    return
  fi

  if [[ "$candidate" != /* ]]; then
    candidate="$(resolve_local_path "$candidate")"
  fi

  if [[ -f "$candidate" ]]; then
    local project_inputs="${PROJECT_ROOT%/}/inputs/"
    local gptsovits_inputs="${GPTSOVITS_WORKSPACE%/}/inputs/"

    if [[ "$candidate" == "${project_inputs}"* ]]; then
      printf '/workspace/reference/%s\n' "${candidate#${project_inputs}}"
      return
    fi

    if [[ "$candidate" == "${gptsovits_inputs}"* ]]; then
      printf '/workspace/reference/%s\n' "${candidate#${gptsovits_inputs}}"
      return
    fi
  fi

  printf '%s\n' "$input"
}

request_v2_tts() {
  local payload="$1"
  local tmp_file="$2"
  local err_file="$3"

  curl -sS \
    -X POST "${BASE_URL%/}/tts" \
    -H 'content-type: application/json' \
    --data "$payload" \
    -o "$tmp_file" \
    -w '%{http_code}' 2>"$err_file"
}

request_v1_tts() {
  local payload="$1"
  local tmp_file="$2"
  local err_file="$3"

  curl -sS \
    -X POST "${BASE_URL%/}/" \
    -H 'content-type: application/json' \
    --data "$payload" \
    -o "$tmp_file" \
    -w '%{http_code}' 2>"$err_file"
}

looks_like_audio_file() {
  local input_file="$1"
  python - "$input_file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = path.read_bytes() if path.exists() else b""

if len(data) < 128:
    raise SystemExit(1)

if data.startswith((b"RIFF", b"OggS", b"ID3", b"\xff\xf1", b"\xff\xf9")):
    raise SystemExit(0)

if data.lstrip().startswith(b"{"):
    raise SystemExit(1)

raise SystemExit(0)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --text)
      TEXT="${2:-}"
      shift 2
      ;;
    --text-lang)
      TEXT_LANG="${2:-}"
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
    --prompt-lang)
      PROMPT_LANG="${2:-}"
      shift 2
      ;;
    --text-split-method)
      TEXT_SPLIT_METHOD="${2:-}"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="${2:-}"
      shift 2
      ;;
    --media-type)
      MEDIA_TYPE="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --project-root)
      PROJECT_ROOT="${2:-}"
      shift 2
      ;;
    --gptsovits-workspace)
      GPTSOVITS_WORKSPACE="${2:-}"
      shift 2
      ;;
    --start-service)
      START_SERVICE=1
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

if [[ -z "$TEXT" || -z "$TEXT_LANG" || -z "$REF_AUDIO" || -z "$PROMPT_LANG" || -z "$PROMPT_TEXT" ]]; then
  echo "Required args: --text --text-lang --ref-audio --prompt-lang --prompt-text" >&2
  usage
  exit 1
fi

require_cmd curl
require_cmd jq

if ! [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]]; then
  echo "--batch-size must be a non-negative integer" >&2
  exit 1
fi

if [[ "$START_SERVICE" -eq 1 ]]; then
  require_cmd docker
  if [[ -f "${GPTSOVITS_WORKSPACE%/}/docker-compose.yml" ]]; then
    (cd "$GPTSOVITS_WORKSPACE" && docker compose up -d >/dev/null)
  elif [[ -f "${PROJECT_ROOT%/}/docker-compose.yml" ]]; then
    (cd "$PROJECT_ROOT" && docker compose up -d >/dev/null)
  else
    echo "docker-compose.yml not found under --gptsovits-workspace or --project-root" >&2
    exit 1
  fi
fi

if [[ "$REF_AUDIO" != /workspace/* ]]; then
  local_ref="$(resolve_local_path "$REF_AUDIO")"
  if [[ ! -f "$local_ref" ]]; then
    echo "Reference audio not found: $local_ref" >&2
    exit 1
  fi
  REF_AUDIO="$local_ref"
fi

REF_AUDIO_API_PATH="$(map_ref_audio_path "$REF_AUDIO")"

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="${PROJECT_ROOT%/}/outputs/tts-$(date +%Y%m%d-%H%M%S).wav"
elif [[ "$OUTPUT" != /* ]]; then
  OUTPUT="${PROJECT_ROOT%/}/${OUTPUT}"
fi

mkdir -p "$(dirname "$OUTPUT")"
TMP_FILE="$(mktemp "${OUTPUT}.tmp.XXXX")"
ERR_FILE_V2="$(mktemp)"
ERR_FILE_V1="$(mktemp)"
trap 'rm -f "$TMP_FILE" "$ERR_FILE_V2" "$ERR_FILE_V1"' EXIT

PAYLOAD_V2="$(
  jq -n \
    --arg text "$TEXT" \
    --arg text_lang "$TEXT_LANG" \
    --arg ref_audio_path "$REF_AUDIO_API_PATH" \
    --arg prompt_lang "$PROMPT_LANG" \
    --arg prompt_text "$PROMPT_TEXT" \
    --arg text_split_method "$TEXT_SPLIT_METHOD" \
    --arg media_type "$MEDIA_TYPE" \
    --argjson batch_size "$BATCH_SIZE" \
    '{
      text: $text,
      text_lang: $text_lang,
      ref_audio_path: $ref_audio_path,
      prompt_lang: $prompt_lang,
      prompt_text: $prompt_text,
      text_split_method: $text_split_method,
      batch_size: $batch_size,
      media_type: $media_type,
      streaming_mode: false
    }'
)"

PAYLOAD_V1="$(
  jq -n \
    --arg text "$TEXT" \
    --arg text_language "$TEXT_LANG" \
    --arg refer_wav_path "$REF_AUDIO_API_PATH" \
    --arg prompt_language "$PROMPT_LANG" \
    --arg prompt_text "$PROMPT_TEXT" \
    '{
      text: $text,
      text_language: $text_language,
      refer_wav_path: $refer_wav_path,
      prompt_language: $prompt_language,
      prompt_text: $prompt_text
    }'
)"

HTTP_CODE_V2="$(request_v2_tts "$PAYLOAD_V2" "$TMP_FILE" "$ERR_FILE_V2" || true)"
if [[ "$HTTP_CODE_V2" == "200" ]] && looks_like_audio_file "$TMP_FILE"; then
  mv "$TMP_FILE" "$OUTPUT"
  echo "Saved (api-v2): $OUTPUT"
  ls -lh "$OUTPUT"
  exit 0
fi

HTTP_CODE_V1="$(request_v1_tts "$PAYLOAD_V1" "$TMP_FILE" "$ERR_FILE_V1" || true)"
if [[ "$HTTP_CODE_V1" == "200" ]] && looks_like_audio_file "$TMP_FILE"; then
  mv "$TMP_FILE" "$OUTPUT"
  echo "Saved (api-v1): $OUTPUT"
  ls -lh "$OUTPUT"
  exit 0
fi

echo "TTS request failed via both endpoints." >&2
echo "  base_url: ${BASE_URL%/}" >&2
echo "  /tts http: ${HTTP_CODE_V2:-N/A}" >&2
if [[ -s "$ERR_FILE_V2" ]]; then
  echo "  /tts curl error:" >&2
  sed -n '1,5p' "$ERR_FILE_V2" >&2
fi
if [[ -s "$TMP_FILE" ]]; then
  echo "  /tts or / body (last response):" >&2
  sed -n '1,40p' "$TMP_FILE" >&2
fi
echo "  / http: ${HTTP_CODE_V1:-N/A}" >&2
if [[ -s "$ERR_FILE_V1" ]]; then
  echo "  / curl error:" >&2
  sed -n '1,5p' "$ERR_FILE_V1" >&2
fi

exit 1
