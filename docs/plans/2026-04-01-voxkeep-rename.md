# VoxKeep Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename the project from `asr-ol` / `asr_ol` to `VoxKeep` across local repo metadata, Python package metadata, runtime entrypoints, docs, tests, and GitHub branch/repository settings.

**Architecture:** Treat the rename as three coordinated layers: GitHub hosting metadata, Python/package/runtime naming, and repository documentation/tests. Preserve the existing runtime behavior while replacing hard-coded `asr-ol`, `asr_ol`, and selected `ASR_OL_*` references where brand-facing consistency matters. Avoid rewriting historical design docs unless required for active workflows.

**Tech Stack:** git, GitHub, Python 3.11, setuptools, pytest, Ruff

---

### Task 1: Capture rename surface and constraints

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `Makefile`
- Modify: `Dockerfile`
- Modify: `scripts/run_local.sh`
- Test: `tests/**`

**Step 1: Inventory all `asr-ol`, `asr_ol`, and `ASR_OL_` references**

Run: `rg -n --hidden --glob '!*.git' 'asr-ol|asr_ol|ASR_OL_' .`

**Step 2: Separate active runtime/config references from historical docs**

Check the hits in `src/`, `tests/`, root configs, and active docs.

**Step 3: Freeze the rename policy**

Keep `docs/plans/**` historical unless a file is part of an active workflow. Preserve user changes already present in the worktree.

### Task 2: Rename active project metadata and package paths

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `Makefile`
- Modify: `Dockerfile`
- Modify: `scripts/run_local.sh`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Move: `src/asr_ol` -> `src/voxkeep`

**Step 1: Update distribution/package metadata**

Rename project metadata to `voxkeep`, CLI entrypoint to `voxkeep`, and type/lint include paths to `src/voxkeep`.

**Step 2: Move the Python package directory**

Rename `src/asr_ol` to `src/voxkeep`.

**Step 3: Update runtime/documentation entrypoints**

Replace `python -m asr_ol` with `python -m voxkeep` and `asr-ol` branding with `VoxKeep` or `voxkeep` as appropriate.

### Task 3: Rewrite source and tests for the new package name

**Files:**
- Modify: `src/voxkeep/**/*.py`
- Modify: `tests/**/*.py`

**Step 1: Replace import paths**

Update all `from asr_ol...` and string assertions containing `asr_ol` to `voxkeep`.

**Step 2: Update architecture tests**

Rewrite hard-coded source roots and package-prefix assertions from `src/asr_ol` / `asr_ol.` to `src/voxkeep` / `voxkeep.`.

**Step 3: Update subprocess/CLI tests**

Replace `python -m asr_ol` expectations with `python -m voxkeep`.

### Task 4: Decide env-prefix scope and apply the active rename

**Files:**
- Modify: `src/voxkeep/shared/config.py`
- Modify: `scripts/run_local.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CONTRIBUTING.md`
- Modify: `tests/**`

**Step 1: Rename active environment-variable prefix**

Replace `ASR_OL_` references with `VOXKEEP_` in runtime code, scripts, CI, and active docs/tests.

**Step 2: Preserve compatibility only if necessary**

If replacement would break current behavior during migration, support both prefixes briefly in code.

### Task 5: Verify and commit the repository rename

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `uv.lock` if regenerated

**Step 1: Run format/lint/tests**

Run: `make fmt`
Run: `make lint`
Run: `make test`

**Step 2: Verify CLI/help path**

Run: `uv run --python 3.11 python -m voxkeep --help`

**Step 3: Commit atomically**

Run: `git add ...`
Run: `git commit -m "refactor: rename project to voxkeep"`

### Task 6: Rename GitHub repo and default branch

**Files:**
- No repository file changes required

**Step 1: Rename GitHub repository**

Use authenticated GitHub tooling/API to rename `zaviro/asr-ol` to `zaviro/voxkeep`.

**Step 2: Rename local branch and remote default branch**

Rename `dev` to `main`, push it, and update upstream/default branch settings on GitHub.

**Step 3: Update local remote URL and verify**

Run: `git remote set-url origin git@github.com:zaviro/voxkeep.git`
Run: `git remote -v`
