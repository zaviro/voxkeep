# ASR-OL UV + Layered Structure Refactor Design

**Date:** 2026-02-18
**Status:** Approved by user

## 1. Goals

1. Keep package name `asr_ol`.
2. Migrate source tree to layered layout:
   - `core/`, `services/`, `api/`, `infra/`, `agents/`, `tools/`, `cli/`
3. Do not provide backward compatibility imports.
4. Adopt `uv` as the primary environment and command runner.
5. Reorganize tests into `tests/unit`, `tests/integration`, `tests/e2e`.

## 2. Non-goals

1. No behavior changes in audio pipeline, FSM, storage, or injection semantics.
2. No GUI/API feature additions in this refactor.
3. No migration shims for old import paths.

## 3. Current-to-target module mapping

- `asr_ol/config.py` -> `asr_ol/core/config.py`
- `asr_ol/events.py` -> `asr_ol/core/events.py`
- `asr_ol/logging_setup.py` -> `asr_ol/core/logging_setup.py`
- `asr_ol/audio/source.py` -> `asr_ol/core/audio_source.py`
- `asr_ol/asr/base.py` -> `asr_ol/core/asr_engine.py`

- `asr_ol/audio/audio_bus.py` -> `asr_ol/services/audio_bus.py`
- `asr_ol/asr/worker.py` -> `asr_ol/services/asr_worker.py`
- `asr_ol/runtime/app.py` -> `asr_ol/services/runtime_app.py`
- `asr_ol/runtime/shutdown.py` -> `asr_ol/services/shutdown.py`
- `asr_ol/injector/worker.py` -> `asr_ol/services/injector_worker.py`

- `asr_ol/audio/audio_capture.py` -> `asr_ol/infra/audio/audio_capture.py`
- `asr_ol/audio/preprocess.py` -> `asr_ol/infra/audio/preprocess.py`
- `asr_ol/asr/funasr_ws.py` -> `asr_ol/infra/asr/funasr_ws.py`
- `asr_ol/vad/silero_worker.py` -> `asr_ol/infra/vad/silero_worker.py`
- `asr_ol/wake/openwakeword_worker.py` -> `asr_ol/infra/wake/openwakeword_worker.py`
- `asr_ol/storage/worker.py` -> `asr_ol/infra/storage/storage_worker.py`

- `asr_ol/capture/fsm.py` -> `asr_ol/agents/capture_fsm.py`
- `asr_ol/capture/worker.py` -> `asr_ol/agents/capture_worker.py`

- `asr_ol/injector/base.py` -> `asr_ol/tools/injector/base.py`
- `asr_ol/injector/factory.py` -> `asr_ol/tools/injector/factory.py`
- `asr_ol/injector/xdotool_injector.py` -> `asr_ol/tools/injector/xdotool_injector.py`
- `asr_ol/injector/ydotool_injector.py` -> `asr_ol/tools/injector/ydotool_injector.py`

- `asr_ol/main.py` -> `asr_ol/cli/main.py`
- Add `asr_ol/__main__.py` as package entrypoint.

## 4. Test layout mapping

- `tests/test_config.py` -> `tests/unit/core/test_config.py`
- `tests/test_boundaries.py` -> `tests/unit/core/test_boundaries.py`
- `tests/test_capture_fsm.py` -> `tests/unit/agents/test_capture_fsm.py`
- `tests/test_injector.py` -> `tests/unit/tools/test_injector.py`

- `tests/test_audio_bus.py` -> `tests/integration/test_audio_bus.py`
- `tests/test_audio_capture.py` -> `tests/integration/test_audio_capture.py`
- `tests/test_storage_worker.py` -> `tests/integration/test_storage_worker.py`
- `tests/test_wake_vad_workers.py` -> `tests/integration/test_wake_vad_workers.py`
- `tests/test_shutdown.py` -> `tests/integration/test_shutdown.py`
- `tests/test_smoke_import.py` -> `tests/integration/test_smoke_import.py`

## 5. UV adoption

1. Keep `pyproject.toml` as single dependency source.
2. Add dependency groups for `dev` and `runtime-ai`.
3. Use `uv run` for commands via Makefile targets.

## 6. Risks and mitigations

1. Import breakage risk: use project-wide import rewrite and run full test suite.
2. Accidental behavior drift: avoid logic edits; move files and update imports only.
3. CI mismatch: add workflow to run pytest with uv-managed environment.

## 7. Validation

1. `uv run pytest` must pass.
2. `python -m asr_ol --help` (or `uv run python -m asr_ol --help`) should work.
3. No remaining imports from removed paths.
