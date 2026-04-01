# Runtime Boundary Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Tighten runtime module boundaries, split config-loading responsibilities, and align tests/docs with the current modular architecture without changing external behavior.

**Architecture:** First remove private implementation reach-through from `bootstrap` and module public APIs, then split `shared.config` into stable submodules behind a compatibility facade, and finally rename legacy test groupings plus doc references to match the current module layout.

**Tech Stack:** Python 3.11, pytest, Ruff, Pyright, uv

---

### Task 1: Tighten Runtime Public Boundaries

**Files:**
- Modify: `src/voxkeep/bootstrap/runtime_app.py`
- Modify: `src/voxkeep/modules/capture/public.py`
- Modify: `src/voxkeep/modules/injection/public.py`
- Modify: `src/voxkeep/modules/transcription/public.py`
- Modify: `tests/unit/bootstrap/test_runtime_app.py`
- Modify: `tests/unit/modules/injection/test_injection_public_api.py`
- Test: `tests/architecture/test_module_dependencies.py`

**Step 1: Write the failing test**

Add tests that prove:
- `AppRuntime` no longer reads `_engine`
- `InjectionModule.execute_capture` does not depend on `_execute_action`

**Step 2: Run test to verify it fails**

Run:
- `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py -q`
- `uv run --python 3.11 python -m pytest tests/unit/modules/injection/test_injection_public_api.py -q`

Expected: FAIL because the current implementation still reaches through private members.

**Step 3: Write minimal implementation**

- Add explicit public/diagnostic accessors where runtime needs them.
- Route injection execution through a public helper path instead of a private worker method.
- Keep lifecycle behavior unchanged.

**Step 4: Run test to verify it passes**

Run:
- `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py -q`
- `uv run --python 3.11 python -m pytest tests/unit/modules/injection/test_injection_public_api.py -q`
- `uv run --python 3.11 python -m pytest tests/architecture -q`

Expected: PASS

**Step 5: Commit**

```bash
git add src/voxkeep/bootstrap/runtime_app.py \
  src/voxkeep/modules/capture/public.py \
  src/voxkeep/modules/injection/public.py \
  src/voxkeep/modules/transcription/public.py \
  tests/unit/bootstrap/test_runtime_app.py \
  tests/unit/modules/injection/test_injection_public_api.py \
  docs/plans/2026-04-01-runtime-boundary-cleanup-design.md \
  docs/plans/2026-04-01-runtime-boundary-cleanup.md
git commit -m "refactor: tighten runtime module boundaries"
```

### Task 2: Split Shared Config Responsibilities

**Files:**
- Create: `src/voxkeep/shared/config_defaults.py`
- Create: `src/voxkeep/shared/config_env.py`
- Create: `src/voxkeep/shared/config_schema.py`
- Create: `src/voxkeep/shared/config_loader.py`
- Modify: `src/voxkeep/shared/config.py`
- Test: `tests/unit/shared/test_config.py`

**Step 1: Write the failing test**

Add tests that prove:
- `load_config` still loads defaults, YAML overrides, and env overrides unchanged
- compatibility imports from `voxkeep.shared.config` still work

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_config.py -q`
Expected: FAIL once compatibility expectations are added before the split.

**Step 3: Write minimal implementation**

- Move schema, defaults, env mapping, and loading helpers into dedicated files.
- Keep `voxkeep.shared.config` as the stable import surface.

**Step 4: Run test to verify it passes**

Run:
- `uv run --python 3.11 python -m pytest tests/unit/shared/test_config.py -q`
- `make validate-config`

Expected: PASS

**Step 5: Commit**

```bash
git add src/voxkeep/shared/config.py \
  src/voxkeep/shared/config_defaults.py \
  src/voxkeep/shared/config_env.py \
  src/voxkeep/shared/config_schema.py \
  src/voxkeep/shared/config_loader.py \
  tests/unit/shared/test_config.py
git commit -m "refactor: split shared config loader responsibilities"
```

### Task 3: Align Test Layout and Docs

**Files:**
- Move: `tests/unit/shared/test_config.py`
- Move: `tests/unit/shared/test_boundaries.py`
- Move: `tests/unit/shared/test_queue_utils.py`
- Move: `tests/unit/bootstrap/test_runtime_app.py`
- Move: `tests/unit/modules/transcription/test_funasr_ws.py`
- Move: `tests/unit/modules/capture/test_openwakeword_scorer.py`
- Move: `tests/unit/modules/storage/test_sqlite_storage_worker.py`
- Move: `tests/unit/modules/capture/test_capture_fsm.py`
- Move: `tests/unit/modules/capture/test_capture_worker_routing.py`
- Move: `tests/unit/modules/capture/test_transcript_extractor.py`
- Move: `tests/unit/modules/injection/test_injector_factory.py`
- Modify: `AGENTS.md`
- Modify: `docs/plans/2026-03-29-modular-monolith-refactor.md`
- Modify: `docs/plans/2026-03-30-modular-monolith-final-shape.md`
- Modify: `docs/plans/2026-02-20-project-onboarding-map.md`
- Modify: `docs/plans/2026-02-18-uv-structure-refactor-design.md`
- Modify: `docs/plans/2026-02-18-uv-structure-refactor.md`

**Step 1: Write the failing test**

Add or update tests/docs checks so old unit-test group names are no longer the expected shape.

**Step 2: Run test to verify it fails**

Run a targeted docs/layout check or the moved tests by their new paths.
Expected: FAIL until paths and references are aligned.

**Step 3: Write minimal implementation**

- Move tests into directories aligned with `shared`, `bootstrap`, and `modules/...`.
- Update documentation references to the new paths.

**Step 4: Run test to verify it passes**

Run:
- `uv run --python 3.11 python -m pytest tests/unit -q`
- `uv run --python 3.11 python -m pytest tests/architecture -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit AGENTS.md docs/plans
git commit -m "refactor: align test layout with module architecture"
```

### Task 4: Final Verification

**Files:**
- No additional edits expected

**Step 1: Run quality checks**

Run:
- `make fmt`
- `make lint`
- `make typecheck`
- `uv run --python 3.11 python -m pytest tests/architecture -q`
- `uv run --python 3.11 python -m pytest tests/unit -q`

**Step 2: Confirm clean working tree**

Run: `git status --short`
Expected: no unstaged surprises before final handoff.
