# ASR-OL UV + Layered Structure Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the repository to layered package layout under `src/asr_ol`, adopt `uv` workflows, and reorganize tests without changing runtime behavior.

**Architecture:** Preserve existing audio/wake/vad/asr/capture/storage behavior. Perform a physical file move with import rewrites from old module paths to new layered paths (`core/services/infra/agents/tools/cli`). Split tests into `unit` and `integration` while keeping assertions unchanged.

**Tech Stack:** Python 3.12, uv, pytest, GitHub Actions.

---

### Task 1: Create target package directories and move source files

**Files:**
- Create: `src/asr_ol/__main__.py`
- Create: `src/asr_ol/api/__init__.py`
- Create: `src/asr_ol/cli/__init__.py`
- Move: source files from old folders into `core/services/infra/agents/tools/cli`

**Step 1: Write failing check**

Run: `uv run python -m asr_ol --help`
Expected: FAIL before migration if `__main__` is missing.

**Step 2: Move files**

- Move and rename modules according to mapping in `2026-02-18-uv-structure-refactor-design.md`.
- Add `__init__.py` in each new package directory.

**Step 3: Add package entrypoint**

`src/asr_ol/__main__.py`
```python
from asr_ol.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Run import smoke check**

Run: `uv run python -m asr_ol --help`
Expected: PASS and print CLI usage.

### Task 2: Rewrite imports in all source modules

**Files:**
- Modify: all moved files under `src/asr_ol/**`

**Step 1: Write failing check**

Run: `uv run pytest tests/integration/test_smoke_import.py -q`
Expected: FAIL with `ModuleNotFoundError` before rewrites.

**Step 2: Update imports**

- Replace old imports like:
  - `asr_ol.config` -> `asr_ol.core.config`
  - `asr_ol.events` -> `asr_ol.core.events`
  - `asr_ol.runtime.app` -> `asr_ol.services.runtime_app`
  - `asr_ol.injector.base` -> `asr_ol.tools.injector.base`
- Ensure internal references match new module locations.

**Step 3: Verify no old paths remain**

Run: `rg "asr_ol\.(audio|asr|capture|injector|runtime|storage|vad|wake|config|events|logging_setup)" src -n`
Expected: only valid new-path references (or none for removed old modules).

### Task 3: Reorganize tests to unit/integration/e2e

**Files:**
- Move: existing `tests/test_*.py` into `tests/unit/**` and `tests/integration/**`
- Create: `tests/e2e/.gitkeep`

**Step 1: Move tests**

- Unit:
  - `tests/unit/core/test_config.py`
  - `tests/unit/core/test_boundaries.py`
  - `tests/unit/agents/test_capture_fsm.py`
  - `tests/unit/tools/test_injector.py`
- Integration:
  - `tests/integration/test_audio_bus.py`
  - `tests/integration/test_audio_capture.py`
  - `tests/integration/test_storage_worker.py`
  - `tests/integration/test_wake_vad_workers.py`
  - `tests/integration/test_shutdown.py`
  - `tests/integration/test_smoke_import.py`

**Step 2: Rewrite test imports**

Update imports to new package paths.

**Step 3: Run tests**

Run: `uv run pytest -q`
Expected: all tests pass.

### Task 4: Update project tooling for uv and local workflows

**Files:**
- Modify: `pyproject.toml`
- Create: `Makefile`
- Create: `.pre-commit-config.yaml`

**Step 1: Update pyproject for uv usage**

- Keep `[project]` metadata.
- Add `[dependency-groups]` for `dev` and `runtime-ai`.
- Add `[tool.pytest.ini_options]` with `testpaths = ["tests"]`.

**Step 2: Add Makefile commands**

Include commands:
- `sync`: `uv sync --group dev`
- `test`: `uv run pytest -q`
- `run`: `uv run python -m asr_ol --config config/config.yaml`
- `lint`: `uv run ruff check src tests`

**Step 3: Add pre-commit config**

- hooks: `ruff`, `ruff-format`, `end-of-file-fixer`, `trailing-whitespace`.

### Task 5: Add CI and README updates

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `README.md`
- Create: `.gitignore`

**Step 1: Add CI**

- Use Ubuntu latest.
- Install `uv`.
- `uv sync --group dev`.
- `uv run pytest -q`.

**Step 2: Add README**

- Document structure, uv commands, runbook essentials, and test commands.

**Step 3: Final validation**

Run:
- `uv run pytest -q`
- `uv run python -m asr_ol --help`

Expected: both pass.
