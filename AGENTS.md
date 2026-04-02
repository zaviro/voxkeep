# Repository Guidelines

## Repo Overview
`VoxKeep` is a local always-on ASR pipeline for Linux desktops. It listens to microphone audio, detects wake words, runs sentence capture with VAD + ASR, and dispatches the final text to injection or other actions such as `openclaw agent`.

Use Python 3.11 and run project commands through `uv`. Do not rely on the system Python or ad-hoc shell state when validating changes.

## Current Architecture
The repository is in the modular-monolith shape described by [docs/plans/2026-03-29-modular-monolith-refactor.md](docs/plans/2026-03-29-modular-monolith-refactor.md).

Primary runtime code lives in `src/voxkeep/`:
- `modules/capture/`: wake/VAD/ASR event orchestration and capture FSM.
- `modules/transcription/`: backend adapters and transcription-facing public API.
- `modules/injection/`: text injection and action execution.
- `modules/storage/`: persistence and storage workers.
- `modules/runtime/`: audio capture, preprocessing, audio bus, and runtime infrastructure.
- `shared/`: shared config, types, logging, and queue utilities.
- `bootstrap/`: top-level runtime wiring.
- `api/` and `cli/`: external entrypoints and operator-facing APIs.

Legacy runtime packages `core/`, `infra/`, and `services/` are retired. Architecture tests require the repository to avoid new runtime code there.

Tests are organized as:
- `tests/unit/`: pure logic and narrow adapters.
- `tests/integration/`: threaded pipeline behavior and runtime coordination.
- `tests/e2e/`: CLI and fixture-backed end-to-end checks.
- `tests/architecture/`: dependency and layout guardrails.

Runtime configuration lives in `config/config.yaml`.

## Non-Negotiables
- Do not add new runtime logic under `src/voxkeep/core/`, `src/voxkeep/infra/`, or `src/voxkeep/services/`.
- Do not make cross-module imports through internals. Cross-module imports under `src/voxkeep/modules/` must go through the target module's `public.py`.
- Do not let `shared/` import from `voxkeep.modules.*`.
- Do not open microphone devices outside `src/voxkeep/modules/runtime/infrastructure/audio_capture.py`.
- Do not write SQLite outside the storage module.
- Do not bypass module public APIs by deep-importing implementation details for convenience.
- Do not silently degrade runtime behavior. If runtime AI, audio, or injector backends fall back, emit a clear log message.
- Do not change config schema, event payload shape, CLI behavior, or wake/action semantics without updating tests and docs.

## Environment Assumptions
- Use `uv run --python 3.11 ...` for Python commands.
- `make sync` is the default install path for everyday development.
- `make sync-ai` is required when working on real wake/VAD/runtime AI behavior, or when you need a local environment that includes `openwakeword`, `silero-vad`, and `torch`.
- The local runtime assumes Linux audio/session tooling is available.
- Real runtime behavior depends on external prerequisites:
  - reachable external ASR service,
  - available microphone source,
  - prepared wake/VAD runtime dependencies,
  - matching injector backend for the current desktop session.
- Preferred long-term ASR path is `qwen_vllm` against an externally managed local service.
- VoxKeep should not start or stop the Qwen `vLLM` service.
- Before diagnosing Qwen runtime failures, validate the external ASR endpoint separately from VoxKeep.
- Session type matters:
  - `XDG_SESSION_TYPE=x11`: expect `xdotool`.
  - `XDG_SESSION_TYPE=wayland`: expect `ydotool` and `ydotoold`, plus required permissions.
- Before diagnosing runtime failures, prefer:
  - `scripts/check_env.sh`
  - `make check-ai`
  - `make validate-config`
  - `make cli-check`

If an environment check fails, do not claim a code fix until the environment problem is isolated from the code change.

## Build, Test, and Development Commands
- `make sync`: install dev dependencies with `uv` on Python 3.11.
- `make sync-ai`: install dev and runtime AI dependencies.
- `make setup-ai-models`: download and validate openwakeword model assets.
- `make check-ai`: verify runtime AI imports and model readiness.
- `make validate-config`: validate `config/config.yaml`.
- `make cli-check`: run CLI-level checks.
- `make test-fast`: run `tests/unit` and `tests/architecture` for the default fast feedback loop.
- `make test-unit`: run `tests/unit`.
- `make test-architecture`: run `tests/architecture`.
- `make test-integration`: run `tests/integration`.
- `make test-e2e`: run `tests/e2e`.
- `make run`: start the local runtime via `scripts/run_local.sh`.
- `make run-ai`: prepare AI assets and start the full local runtime.
- `make fmt`: run Ruff formatter on `src`, `tests`, and `scripts`.
- `make lint`: run Ruff checks on `src`, `tests`, and `scripts`.
- `make typecheck`: run Pyright.
- `make test`: run the full pytest suite.
- `make test-cov`: run pytest with coverage.
- `make precommit`: run all pre-commit hooks.

Useful targeted commands:
- `uv run --python 3.11 python -m pytest tests/unit/modules/capture/test_capture_fsm.py -q`
- `uv run --python 3.11 python -m pytest tests/integration/test_audio_bus.py -q`
- `uv run --python 3.11 python -m pytest tests/architecture -q`

## Architecture Invariants
- Runtime wiring belongs in `bootstrap/`. Do not move business logic back into bootstrap builders.
- `modules/runtime/` owns microphone capture, preprocessing, and audio fan-out.
- `modules/capture/` owns wake/VAD/ASR event coordination and the capture state machine.
- `modules/transcription/` owns ASR backend communication.
- `modules/injection/` owns text injection and action execution.
- `modules/storage/` owns durable persistence.
- Module-to-module collaboration must go through public contracts, not implementation imports.
- `shared/` may provide reusable primitives, but it must not become a backdoor dependency hub into runtime modules.
- Keep domain and application logic separate from OS/process/tool-specific adapters when adding new behavior.

## Common Pitfalls
- Do not add new code by copying legacy imports from old tests or stale docs. Follow the `modules/` layout first.
- Do not use real microphone, real FunASR, or real desktop injection in unit tests.
- Do not put desktop-session branching logic in unrelated modules. Keep injector/backend selection inside the injection layer.
- Do not hardcode wake model assumptions in multiple places. Resolve enabled rules from config or shared config APIs.
- Do not treat runtime dependency failures as ordinary unit-test regressions. Check environment readiness first.
- Do not expand large orchestrator files when a new domain concept deserves its own module.
- Do not update only code when behavior changes also affect docs, config, scripts, or operator workflow.

## Testing Guidelines
Testing uses `pytest` with `testpaths = ["tests"]`.

Default frequency tiers:
- High-frequency: `tests/unit` and `tests/architecture`. These should stay fast, stable, and free of real runtime dependencies.
- Change-triggered: `tests/integration`. Run when changing queues, workers, lifecycle handling, runtime wiring, storage behavior, or module coordination.
- Low-frequency acceptance: `tests/e2e` and any test requiring real OpenClaw, GPT-SoVITS fixtures, real AI/runtime dependencies, or external services. Run these when the relevant environment changes or when modifying the corresponding runtime path.

Choose the narrowest test set that proves the change:
- Pure logic or state transitions: add or update unit tests.
- Queueing, worker lifecycle, shutdown, or module wiring: run integration tests.
- Module boundary or repository shape changes: run `tests/architecture`.
- CLI-facing behavior: run the CLI e2e/unit coverage.
- Fixture-backed speech pipeline work: run the relevant e2e only when prerequisites are ready.

### GPT-SoVITS Fixture E2E
- E2E must use pre-generated fixtures under `tests/fixtures/audio/gptsovits/`.
- Required fixture files:
  - `alexa_inject_text_zh.wav`
  - `hey_jarvis_openclaw_zh.wav`
- Generate or refresh fixtures with `.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh`.
- Preferred API startup is `~/workspace/gptsovits/scripts/start_api_cuda.sh`.
- Run fixture E2E with:
  - `VOXKEEP_RUN_GPTSOVITS_E2E=1 uv run --python 3.11 python -m pytest tests/e2e/test_pipeline_tts_audio.py -q`

## Definition of Done
- Python code changes: run `make fmt`, `make lint`, and `make typecheck`.
- If local `make typecheck` fails because runtime-ai packages are intentionally not installed, do not treat that as a code regression. Either install `make sync-ai` or explicitly report the environment limitation.
- Logic changes: add or update the narrowest relevant tests before claiming completion.
- Runtime pipeline changes: run the most relevant integration tests.
- Architecture or module-boundary changes: run `uv run --python 3.11 python -m pytest tests/architecture -q`.
- Runtime AI or injector behavior changes: verify environment prerequisites before treating failures as code regressions.
- Config, workflow, or operator-facing behavior changes: update docs and configuration examples.
- If you introduce a new recurring pitfall or workflow rule, update this `AGENTS.md`.

## Commit Guidelines
Use Conventional Commits such as `feat: ...`, `fix: ...`, `refactor: ...`, `test: ...`, or `chore: ...`.

Keep commits atomic and test-backed:
- stage only the files for the completed subtask,
- include the relevant test/documentation updates,
- record the validation command you actually ran.

Do not amend or rewrite unrelated user work.
