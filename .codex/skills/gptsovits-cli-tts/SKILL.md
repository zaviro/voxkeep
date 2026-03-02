---
name: gptsovits-cli-tts
description: Generate and maintain prebuilt GPT-SoVITS audio fixtures for E2E tests. This skill is for one-time fixture preparation, not per-test synthesis.
---

# GPT-SoVITS Test Audio Fixtures

## Purpose

Use this skill to create deterministic, reusable audio fixtures for E2E tests.

This skill is **not** for generating audio during each test run.
Tests should consume committed/pre-generated fixture files under:

- `tests/fixtures/audio/gptsovits/alexa_inject_text_zh.wav`
- `tests/fixtures/audio/gptsovits/hey_jarvis_openclaw_zh.wav`

## Default Assets Requirement

By default, fixture generation expects built-in assets:

- Default reference audio (one of):
  - `inputs/default_reference.wav`
  - `inputs/reference.wav`
- Default model assets:
  - at least one model file under `models/` with extension `.pth/.pt/.ckpt/.safetensors/.onnx`

If missing, generation fails fast with explicit errors.

## Workflow

1. Ensure GPT-SoVITS API is reachable (`http://127.0.0.1:9880/tts`).
2. Generate fixtures once (or regenerate with `--force`).
3. Run E2E tests that read fixture files directly.

## Commands

### Generate fixtures once

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh
```

### Start service before generation

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh --start-service
```

### Force regeneration

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh --force
```

### Override defaults

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh \
  --ref-audio /abs/path/to/ref.wav \
  --prompt-text "你好，这是参考语音对应文本" \
  --text-lang zh \
  --prompt-lang zh
```

## Notes

- Under this repo workflow, generation is a **pre-test setup step**.
- Do not call `tts_request.sh` from test code paths.
- Keep fixture file names stable to avoid flaky E2E behavior.

## Resources

- `scripts/generate_test_fixtures.sh`: one-time fixture generator
- `scripts/tts_request.sh`: low-level TTS API wrapper
- `references/api-v2-quick-reference.md`: GPT-SoVITS API reference
