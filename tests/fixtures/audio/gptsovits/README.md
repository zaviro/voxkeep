# GPT-SoVITS E2E Audio Fixtures

This folder stores pre-generated fixture audio used by `tests/e2e/test_pipeline_tts_audio.py`.

Required fixture files:

- `alexa_inject_text_zh.wav`
- `hey_jarvis_openclaw_zh.wav`

Generate/update these fixtures once with:

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh
```

The generator will normalize files to `16kHz` mono wav for stable pipeline behavior.

The E2E test suite consumes these files directly and does not synthesize audio during test execution.
