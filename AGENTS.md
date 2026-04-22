# Repository Guidelines

## Repo Overview
`VoxKeep` is a local always-on ASR pipeline for Linux desktops. It listens to microphone audio, detects wake words, runs sentence capture with VAD + ASR, and dispatches the final text to injection or other actions such as `openclaw agent`.

Use Python 3.11 and run project commands through `uv`. Do not rely on the system Python or ad-hoc shell state when validating changes.

## Current Architecture
The repository follows a **modular-monolith** shape. Primary runtime code lives in `src/voxkeep/`:
- `modules/capture/`: wake/VAD/ASR event orchestration and capture FSM.
- `modules/transcription/`: backend adapters and transcription-facing public API.
- `modules/injection/`: text injection and action execution.
- `modules/storage/`: persistence and storage workers.
- `modules/audio_engine/`: audio capture, preprocessing, audio bus, and audio engine infrastructure.
- `shared/`: shared config, types, logging, and queue utilities.
- `bootstrap/`: top-level runtime wiring and lifecycle orchestration.
- `api/` and `cli/`: external entrypoints and operator-facing APIs.

**Note**: Legacy runtime packages `core/`, `infra/`, and `services/` are retired. Do not add new code there.

## Non-Negotiables
- Do not add new runtime logic under `src/voxkeep/core/`, `src/voxkeep/infra/`, or `src/voxkeep/services/`.
- Cross-module imports under `src/voxkeep/modules/` must go through the target module's `public.py`.
- `shared/` must NOT import from `voxkeep.modules.*`.
- Do not open microphone devices outside `src/voxkeep/modules/audio_engine/infrastructure/audio_capture.py`.
- Do not write SQLite outside the storage module.
- Do not bypass module public APIs by deep-importing implementation details.
- Emit clear log messages if any backend falls back or fails.
- Do not change config schema, event payload shape, CLI behavior, or wake/action semantics without updating tests and docs.

## Environment Assumptions
- Use `uv run --python 3.11 ...` for all Python commands.
- `make sync-ai` is required for local AI behavior (includes `openwakeword`, `silero-vad`, `torch`).
- Preferred ASR path is **`qwen_vllm`** against an externally managed local service (default: `ws://127.0.0.1:8000/v1/realtime`).
- VoxKeep does not manage the Qwen `vLLM` service lifecycle.
- FunASR is no longer supported or managed by VoxKeep.
- Session type impacts injection: `xdotool` for X11, `ydotool` for Wayland.

## Build, Test, and Development Commands
- `make sync-ai`: install dev and runtime AI dependencies.
- `make setup-ai-models`: download and validate openwakeword model assets.
- `make doctor`: run environment diagnostics.
- `make validate-config`: validate `config/config.yaml`.
- `make test-fast`: run unit and architecture tests (default feedback loop).
- `make test`: run the full pytest suite.
- `make run`: start the runtime using current config.
- `make fmt` / `make lint`: run Ruff formatter and checks.
- `make typecheck`: run Pyright.

## Adding New Features
1. **Define Events**: Add necessary event types in `src/voxkeep/shared/events.py`.
2. **Implement Logic**: Add logic within a specific module in `src/voxkeep/modules/`, ensuring internal implementation is hidden.
3. **Expose Public API**: Update the module's `public.py` to expose necessary builders or functions.
4. **Wire Component**: Update `src/voxkeep/bootstrap/runtime_app.py` to integrate the new component into the pipeline.
5. **Validate Architecture**: Run `make test-architecture` to ensure no boundary violations.
6. **Add Tests**: Add unit tests for logic and integration tests for pipeline behavior.

## Testing Guidelines
- **Unit Tests** (`tests/unit/`): Pure logic, state machines, and narrow adapters. No real hardware or external services.
- **Architecture Tests** (`tests/architecture/`): Enforce module layout and dependency rules.
- **Integration Tests** (`tests/integration/`): Threaded pipeline behavior, worker coordination, and shutdown.
- **E2E Tests** (`tests/e2e/`): CLI behavior and fixture-backed pipeline checks (requires `VOXKEEP_RUN_GPTSOVITS_E2E=1`).

## Commit Guidelines
Use Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `chore:`). Keep commits atomic and include relevant test/doc updates.
