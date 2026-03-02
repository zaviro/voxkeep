# GPT-SoVITS API v2 Quick Reference

Primary source: `api_v2.py` from the official GPT-SoVITS repository.

## Service Default

- Base URL: `http://127.0.0.1:9880`

## TTS Endpoint

- Endpoint: `POST /tts`
- Response:
  - `200`: returns audio binary stream
  - `400`: returns JSON error

### Minimal Required Request Fields

```json
{
  "text": "你好",
  "text_lang": "zh",
  "ref_audio_path": "/workspace/reference/ref.wav",
  "prompt_lang": "zh",
  "prompt_text": "你好，这是一段参考提示词。"
}
```

### Common Optional Fields

- `text_split_method`: default `cut5`
- `batch_size`: default `1`
- `media_type`: default `wav`
- `streaming_mode`: default `false`
- `speed_factor`: speaking speed factor

## Model Switching Endpoints

- `GET /set_gpt_weights?weights_path=<path>`
- `GET /set_sovits_weights?weights_path=<path>`

## Process Control Endpoint

- `GET /control?command=restart`
- `GET /control?command=exit`

## Docker Path Notes for This Project

From this repository's `docker-compose.yml`:

- `./inputs` -> `/workspace/reference`
- `./outputs` -> `/workspace/output`
- `./models` -> `/workspace/GPT_SoVITS/pretrained_models`

When calling `/tts`, `ref_audio_path` must be visible inside the service runtime.
