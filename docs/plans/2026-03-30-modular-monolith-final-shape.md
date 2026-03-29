# ASR-OL 模块化单体最终形态实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `core / infra / services` 中残留的真实实现完全迁移到 `shared / modules / bootstrap`，使仓库达到模块化单体最终形态。

**Architecture:** 先用失败测试锁定 “shared 与 bootstrap 不再依赖旧层” 的目标，再迁移共享契约、运行时输入基础设施、capture 输入基础设施，最后删除旧层并验证。

**Tech Stack:** Python 3.11, pytest, Ruff, threading, queue, pathlib

---

### Task 1: 锁定最终形态架构规则

**Files:**
- Modify: `tests/architecture/test_module_dependencies.py`
- Create: `tests/architecture/test_final_shape.py`

**Step 1: Write the failing test**

```python
def test_bootstrap_does_not_import_legacy_layers() -> None:
    assert collect_legacy_imports("bootstrap") == []
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py -q`
Expected: FAIL because bootstrap still imports core/infra/services

**Step 3: Write minimal implementation**

- 扩展 AST 架构扫描，禁止 `bootstrap` 与 `shared` 依赖旧层
- 新增最终形态测试

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py tests/architecture/test_module_dependencies.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-03-30-modular-monolith-final-shape-design.md docs/plans/2026-03-30-modular-monolith-final-shape.md tests/architecture/test_final_shape.py tests/architecture/test_module_dependencies.py
git commit -m "test: enforce final modular monolith shape"
```

### Task 2: 迁移 shared 真实实现

**Files:**
- Modify: `src/asr_ol/shared/config.py`
- Create: `src/asr_ol/shared/events.py`
- Create: `src/asr_ol/shared/interfaces.py`
- Modify: `src/asr_ol/shared/logging_setup.py`
- Modify: `src/asr_ol/shared/queue_utils.py`
- Modify: imports across `src/` and `tests/`
- Delete: `src/asr_ol/core/*.py`

**Step 1: Write the failing test**

```python
def test_shared_does_not_depend_on_core() -> None:
    assert find_shared_core_imports() == []
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py -q`
Expected: FAIL because shared currently re-exports core

**Step 3: Write minimal implementation**

- 将 `core` 内容迁入 `shared`
- 批量改写 imports
- 删除 `core`

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/unit/core/test_config.py tests/unit/core/test_queue_utils.py tests/unit/core/test_boundaries.py -q`
Expected: PASS after tests改到 `shared`

**Step 5: Commit**

```bash
git add src/asr_ol/shared src/asr_ol/core tests
git commit -m "refactor: move shared contracts out of core"
```

### Task 3: 收拢 runtime 输入基础设施

**Files:**
- Create: `src/asr_ol/modules/runtime/infrastructure/audio_bus.py`
- Create: `src/asr_ol/modules/runtime/infrastructure/audio_capture.py`
- Create: `src/asr_ol/modules/runtime/infrastructure/lifecycle.py`
- Create: `src/asr_ol/modules/runtime/infrastructure/preprocess.py`
- Modify: `src/asr_ol/bootstrap/runtime_app.py`
- Modify: runtime-related tests
- Delete: `src/asr_ol/services/audio_bus.py`
- Delete: `src/asr_ol/services/lifecycle.py`
- Delete: `src/asr_ol/infra/audio/audio_capture.py`
- Delete: `src/asr_ol/infra/audio/preprocess.py`

**Step 1: Write the failing test**

```python
def test_bootstrap_uses_runtime_module_infrastructure_only() -> None:
    assert collect_legacy_imports("bootstrap") == []
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py tests/unit/services/test_runtime_app.py -q`
Expected: FAIL until runtime imports move

**Step 3: Write minimal implementation**

- 迁移运行时输入基础设施
- 更新 bootstrap 与测试导入

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/integration/test_audio_bus.py tests/integration/test_audio_capture.py tests/unit/services/test_runtime_app.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/modules/runtime src/asr_ol/bootstrap tests
git commit -m "refactor: move runtime input infrastructure into module"
```

### Task 4: 收拢 capture 输入基础设施

**Files:**
- Create: `src/asr_ol/modules/capture/infrastructure/openwakeword_worker.py`
- Create: `src/asr_ol/modules/capture/infrastructure/silero_worker.py`
- Modify: `src/asr_ol/bootstrap/runtime_app.py`
- Modify: capture/wake/vad tests
- Delete: `src/asr_ol/infra/vad/silero_worker.py`
- Delete: `src/asr_ol/infra/wake/openwakeword_worker.py`

**Step 1: Write the failing test**

```python
def test_modules_do_not_import_legacy_infra() -> None:
    assert collect_legacy_imports("modules") == []
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py -q`
Expected: FAIL because bootstrap/modules still import infra wake/vad

**Step 3: Write minimal implementation**

- 迁移 wake/vad workers
- 更新 bootstrap 与测试导入
- 删除旧 infra 路径

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/integration/test_wake_vad_workers.py tests/unit/infra/test_openwakeword_scorer.py tests/unit/services/test_runtime_app.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/modules/capture src/asr_ol/bootstrap tests
git commit -m "refactor: move capture input infrastructure into module"
```

### Task 5: 删除旧层并完成最终验证

**Files:**
- Modify: imports across `src/` and `tests/`
- Delete: empty legacy layer files and package dirs where safe

**Step 1: Write the failing test**

```python
def test_repository_has_no_legacy_runtime_layers() -> None:
    assert legacy_runtime_files() == []
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py -q`
Expected: FAIL until legacy files removed

**Step 3: Write minimal implementation**

- 删除 `core / infra / services` 剩余实现
- 保留必要的空 `__init__.py` 仅在确有导入契约时才允许

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_final_shape.py -q && uv run --python 3.11 ruff check src tests && uv run --python 3.11 python -m asr_ol --help`
Expected: PASS / exit 0

**Step 5: Commit**

```bash
git add src tests docs/plans
git commit -m "refactor: finalize modular monolith architecture"
```
