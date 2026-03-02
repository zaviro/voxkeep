#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:9880"
PROJECT_ROOT="$(pwd)"
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
  cat <<'EOF'
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
    [--text-split-method cut5] \
    [--batch-size 1] \
    [--media-type wav] \
    [--start-service]
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1" >&2
    exit 1
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
    candidate="${PROJECT_ROOT%/}/${candidate}"
  fi

  if [[ -f "$candidate" ]]; then
    local inputs_dir="${PROJECT_ROOT%/}/inputs/"
    if [[ "$candidate" == "${inputs_dir}"* ]]; then
      printf '/workspace/reference/%s\n' "${candidate#${inputs_dir}}"
      return
    fi
  fi

  printf '%s\n' "$input"
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
  if [[ ! -f "${PROJECT_ROOT%/}/docker-compose.yml" ]]; then
    echo "docker-compose.yml not found under --project-root: $PROJECT_ROOT" >&2
    exit 1
  fi
  (cd "$PROJECT_ROOT" && docker compose up -d >/dev/null)
fi

if [[ "$REF_AUDIO" != /workspace/* ]]; then
  local_ref="$REF_AUDIO"
  if [[ "$local_ref" != /* ]]; then
    local_ref="${PROJECT_ROOT%/}/${local_ref}"
  fi
  if [[ ! -f "$local_ref" ]]; then
    echo "Reference audio not found: $local_ref" >&2
    exit 1
  fi
fi

REF_AUDIO_API_PATH="$(map_ref_audio_path "$REF_AUDIO")"

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="${PROJECT_ROOT%/}/outputs/tts-$(date +%Y%m%d-%H%M%S).wav"
elif [[ "$OUTPUT" != /* ]]; then
  OUTPUT="${PROJECT_ROOT%/}/${OUTPUT}"
fi

mkdir -p "$(dirname "$OUTPUT")"
TMP_FILE="$(mktemp "${OUTPUT}.tmp.XXXX")"

PAYLOAD="$(
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

HTTP_CODE="$(
  curl -sS \
    -X POST "${BASE_URL%/}/tts" \
    -H 'content-type: application/json' \
    --data "$PAYLOAD" \
    -o "$TMP_FILE" \
    -w '%{http_code}'
)"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "TTS request failed, HTTP $HTTP_CODE" >&2
  if [[ -s "$TMP_FILE" ]]; then
    cat "$TMP_FILE" >&2
  fi
  rm -f "$TMP_FILE"
  exit 1
fi

mv "$TMP_FILE" "$OUTPUT"
echo "Saved: $OUTPUT"
ls -lh "$OUTPUT"
