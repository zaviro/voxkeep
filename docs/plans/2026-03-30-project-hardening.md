# Project Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stabilize default test execution and expand static type coverage across the active package.

**Architecture:** Add a shared pytest fixture that explicitly gates real `openclaw` calls, then widen `pyright` coverage to the full package and fix surfaced typing issues in the FunASR websocket adapter.

**Tech Stack:** Python 3.11, pytest, pyright, Ruff

---

### Task 1: Gate Real OpenClaw Tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/integration/test_openclaw_real_call.py`
- Modify: `tests/e2e/test_pipeline_tts_audio.py`
- Modify: `README.md`

**Step 1: Reproduce the current failure**

Run: `uv run --python 3.11 python -m pytest -q`
Expected: `tests/integration/test_openclaw_real_call.py` fails because the real `openclaw` agent call is environment-sensitive.

**Step 2: Add explicit gating**

- Add a shared fixture in `tests/conftest.py`.
- Skip real `openclaw` tests unless `ASR_OL_RUN_OPENCLAW_REAL=1`.
- Reuse the fixture in the direct integration test and the GPT-SoVITS OpenClaw E2E path.

**Step 3: Document the opt-in flow**

- Add README test commands for real `openclaw` runs.

**Step 4: Verify**

Run: `uv run --python 3.11 python -m pytest tests/integration/test_openclaw_real_call.py -q`
Expected: skipped by default.

### Task 2: Expand Pyright Coverage

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/asr_ol/modules/transcription/infrastructure/funasr_ws.py`

**Step 1: Reproduce the current typing issues**

Run: `uv run --python 3.11 pyright src/asr_ol`
Expected: two errors in `funasr_ws.py`.

**Step 2: Apply minimal fixes**

- Use `websockets.typing.Subprotocol` for the websocket subprotocol value.
- Guard `task.exception()` before re-raising.

**Step 3: Widen the configured coverage**

- Change `tool.pyright.include` to `["src/asr_ol"]`.

**Step 4: Verify**

Run: `uv run --python 3.11 pyright`
Expected: `0 errors`.

### Task 3: Final Verification

**Files:**
- No additional edits expected

**Step 1: Run quality checks**

Run:
- `uv run --python 3.11 python -m pytest -q`
- `uv run --python 3.11 ruff check src tests scripts`
- `uv run --python 3.11 pyright`

**Step 2: Commit**

```bash
git add docs/plans/2026-03-30-project-hardening-design.md \
  docs/plans/2026-03-30-project-hardening.md \
  README.md pyproject.toml \
  tests/conftest.py tests/integration/test_openclaw_real_call.py \
  tests/e2e/test_pipeline_tts_audio.py \
  src/asr_ol/modules/transcription/infrastructure/funasr_ws.py
git commit -m "fix: harden test and typecheck workflows"
```
