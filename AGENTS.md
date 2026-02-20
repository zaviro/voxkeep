# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `src/asr_ol/`:
- `core/`: shared contracts and config (`AudioSource`, `ASREngine`, events).
- `services/`: runtime orchestration (`runtime_app`, `audio_bus`, shutdown flow).
- `infra/`: adapters for audio capture, FunASR websocket, VAD/wake workers, SQLite.
- `agents/`: wake-triggered capture state machine and capture worker.
- `tools/injector/`: text injection backends (`xdotool`, `ydotool`).
- `cli/` and `__main__.py`: entrypoints.

Tests are in `tests/unit/`, `tests/integration/`, and `tests/e2e/`. Runtime config is `config/config.yaml`; design and implementation notes are in `docs/plans/`.

## Build, Test, and Development Commands
- `make sync`: install dev dependencies with `uv` (Python 3.11).
- `make sync-ai`: install dev + runtime AI dependencies.
- `make setup-ai-models`: download/prepare openwakeword models.
- `make run`: start local app (`uv run --python 3.11 python -m asr_ol --config config/config.yaml`).
- `make run-ai`: start full wake/VAD/ASR pipeline after model setup.
- `make test`: run `pytest -q`.
- `make lint`: run `ruff check src tests`.
- `make fmt`: run `ruff format src tests`.
- `make precommit`: run all pre-commit hooks.
- `scripts/check_env.sh`: validate session/audio/FunASR/injector prerequisites.

## Coding Style & Naming Conventions
Use Python 3.11+, 4-space indentation, and type hints on public interfaces. Follow naming conventions: files/modules in `snake_case`, classes in `PascalCase`, constants in `UPPER_SNAKE_CASE`. Keep runtime boundaries strict: only `audio_capture` opens `sounddevice`; only `storage_worker` writes SQLite.

Linting/formatting is enforced by Ruff (`line-length = 100`, rules `E`/`F`) plus pre-commit checks (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`).

## Testing Guidelines
Testing framework is `pytest` (configured in `pyproject.toml` with `testpaths = ["tests"]`). Name files `test_*.py` and functions `test_*`. Add unit tests for pure logic (for example, `capture_fsm`) and integration tests for threaded pipeline behavior (`audio_bus`, shutdown, storage worker).

Example targeted run:
`uv run --python 3.11 pytest tests/unit/agents/test_capture_fsm.py -q`

## Commit & Pull Request Guidelines
Current history uses Conventional Commits (`fix: ...`, `chore: ...`); keep using `type: summary` (for example, `feat: add ydotool fallback logging`). Keep commits focused and test-backed.

PRs should include:
- concise summary and scope,
- linked issue or plan doc (`docs/plans/...`),
- test evidence (command + result),
- runtime/config impact notes (audio devices, session type, FunASR endpoint) when relevant.
