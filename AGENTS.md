# Repository Guidelines

## Project Structure & Module Organization
Core code lives under `src/asr_ol/`:
- `core/`: shared contracts and config loading (`AudioSource`, `ASREngine`, event models).
- `services/`: runtime orchestration (`runtime_app`, `audio_bus`, `asr_worker`, shutdown flow).
- `infra/`: concrete adapters (audio capture, FunASR websocket, VAD/wake workers, SQLite storage).
- `agents/`: wake-triggered capture state machine and capture worker.
- `tools/injector/`: text injection backends (`xdotool`, `ydotool`).
- `cli/` and `__main__.py`: entrypoints.

Tests are in `tests/unit/`, `tests/integration/`, with `tests/e2e/` reserved for end-to-end scenarios. Runtime config is `config/config.yaml`; planning docs are in `docs/plans/`.

## Build, Test, and Development Commands
- `make sync`: install dev dependencies via `uv`.
- `make sync-ai`: install dev + runtime AI deps.
- `make run`: run local app (`uv run python -m asr_ol --config config/config.yaml`).
- `make test`: run all tests (`pytest -q`).
- `make lint`: run `ruff check src tests`.
- `make fmt`: format with `ruff format`.
- `make precommit`: run all pre-commit hooks.
- `scripts/check_env.sh`: verify session/audio/FunASR/injector prerequisites.

## Coding Style & Naming Conventions
Use Python 3.12+, 4-space indentation, and type hints on public interfaces. Follow existing naming: modules/files in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE_CASE`. Keep runtime boundaries strict: only `audio_capture` opens `sounddevice`, and only `storage_worker` writes SQLite.

Formatting/linting is enforced by Ruff (`line-length = 100`, rules `E`/`F`) and pre-commit hooks (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`).

## Testing Guidelines
Framework: `pytest` (configured in `pyproject.toml` with `testpaths = ["tests"]`). Name files `test_*.py` and test functions `test_*`. Add unit tests for pure logic (for example, `capture_fsm`) and integration tests for threaded pipeline behavior (`audio_bus`, shutdown, storage worker).

Run targeted tests with:
`uv run pytest tests/unit/agents/test_capture_fsm.py -q`

## Commit & Pull Request Guidelines
Current `main` has no established commit history yet; use Conventional Commits moving forward (for example, `feat: add ydotool fallback logging`, `fix: prevent duplicate capture inject`). Keep commits focused and test-backed.

PRs should include:
- clear summary and scope,
- linked issue or plan doc (`docs/plans/...`),
- test evidence (command + result),
- config/runtime impact notes (audio devices, session type, FunASR endpoint) when relevant.
