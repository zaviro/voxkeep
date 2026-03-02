---
name: gptsovits-cli-tts
description: Generate and maintain prebuilt GPT-SoVITS audio fixtures for E2E tests. This skill is for one-time fixture preparation, not per-test synthesis.
---

# GPT-SoVITS Test Audio Fixtures

## Purpose

Use this skill to create deterministic, reusable audio fixtures for E2E tests.

This skill is **not** for generating audio during each test run.
Tests should consume pre-generated fixture files under:

- `tests/fixtures/audio/gptsovits/alexa_inject_text_zh.wav`
- `tests/fixtures/audio/gptsovits/hey_jarvis_openclaw_zh.wav`

## Repository Convention

Fixture generation is a one-time setup command and part of repository testing conventions.

- Source of truth: `tests/fixtures/audio/gptsovits/*.wav`
- Generation tool: `scripts/generate_test_fixtures.sh`
- Test execution must read fixtures directly; test code must not call TTS API at runtime

## Default Assets and Bootstrap

The generator supports default asset bootstrap:

- models under `models/` (auto-copied from Docker image when missing)
- reference audio under `inputs/default_reference.wav` (auto-extracted from available model zip when possible)
- sync to external GPT-SoVITS workspace mount (default: `$HOME/workspace/gptsovits`)

If assets still cannot be resolved, it fails with explicit diagnostics.

## API Compatibility

- Preferred endpoint: `POST /tts` (API v2)
- Fallback endpoint: `POST /` (legacy API v1)
- If API is unreachable, generator can auto-start `api.py` in running container (`gptsovits-v2pro-plus` by default), and prefers `$HOME/workspace/gptsovits/scripts/start_api_cuda.sh` when available.

## Commands

Generate fixtures once:

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh
```

Regenerate fixtures:

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh --force
```

Specify workspace/container explicitly:

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh \
  --gptsovits-workspace /abs/path/to/gptsovits \
  --container-name gptsovits-v2pro-plus
```

Force CPU startup when GPU inference is unavailable:

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh --device cpu
```

Run E2E with fixture gating:

```bash
ASR_OL_RUN_GPTSOVITS_E2E=1 uv run --python 3.11 pytest tests/e2e/test_pipeline_tts_audio.py -q
```

## Notes

- Generated fixtures are normalized to `16kHz`, mono, wav to match pipeline config.
- Keep fixture names stable to avoid E2E churn.
- Do not call `tts_request.sh` from test code paths.

## Resources

- `scripts/generate_test_fixtures.sh`: one-time fixture generator
- `scripts/tts_request.sh`: low-level TTS API wrapper (v2 + v1 fallback)
- `references/api-v2-quick-reference.md`: GPT-SoVITS API reference
