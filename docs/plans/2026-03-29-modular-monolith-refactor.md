# ASR-OL 模块化单体重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改变 CLI、配置与单进程多线程运行语义的前提下，将当前代码库逐步迁移为具备强模块边界与架构约束的模块化单体。

**Architecture:** 先建立 `modules/`、`shared/`、`bootstrap/` 新结构与架构测试，再按 `storage -> injection -> capture -> transcription -> runtime` 顺序迁移。模块之间只允许通过 `public.py` 协作，旧结构在迁移完成后逐步删除。

**Tech Stack:** Python 3.11, pytest, Ruff, pathlib, dataclasses, existing threading/queue runtime

---

### Task 1: 建立新目录骨架与公开入口

**Files:**
- Create: `src/asr_ol/modules/__init__.py`
- Create: `src/asr_ol/modules/transcription/__init__.py`
- Create: `src/asr_ol/modules/transcription/public.py`
- Create: `src/asr_ol/modules/transcription/contracts.py`
- Create: `src/asr_ol/modules/capture/__init__.py`
- Create: `src/asr_ol/modules/capture/public.py`
- Create: `src/asr_ol/modules/capture/contracts.py`
- Create: `src/asr_ol/modules/injection/__init__.py`
- Create: `src/asr_ol/modules/injection/public.py`
- Create: `src/asr_ol/modules/injection/contracts.py`
- Create: `src/asr_ol/modules/storage/__init__.py`
- Create: `src/asr_ol/modules/storage/public.py`
- Create: `src/asr_ol/modules/storage/contracts.py`
- Create: `src/asr_ol/modules/runtime/__init__.py`
- Create: `src/asr_ol/modules/runtime/public.py`
- Create: `src/asr_ol/modules/runtime/contracts.py`
- Create: `src/asr_ol/bootstrap/__init__.py`
- Create: `src/asr_ol/bootstrap/runtime_app.py`
- Create: `src/asr_ol/shared/__init__.py`
- Create: `src/asr_ol/shared/config.py`
- Create: `src/asr_ol/shared/logging_setup.py`
- Create: `src/asr_ol/shared/queue_utils.py`
- Create: `src/asr_ol/shared/types.py`
- Test: `tests/architecture/test_module_layout.py`

**Step 1: Write the failing test**

```python
def test_new_module_public_entrypoints_exist() -> None:
    from asr_ol.modules.capture.public import CaptureModule
    from asr_ol.modules.injection.public import InjectionModule
    from asr_ol.modules.runtime.public import RuntimeModule
    from asr_ol.modules.storage.public import StorageModule
    from asr_ol.modules.transcription.public import TranscriptionModule

    assert CaptureModule
    assert InjectionModule
    assert RuntimeModule
    assert StorageModule
    assert TranscriptionModule
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_module_layout.py -q`
Expected: FAIL with missing module path errors

**Step 3: Write minimal implementation**

- 新增模块骨架与最小 `Protocol` / `dataclass` 公开类型
- 让 `shared` 先转发旧 `core` 能力，避免阶段 1 就改运行逻辑
- 新增 `bootstrap/runtime_app.py` 先转发现有 `services.runtime_app.AppRuntime`

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_module_layout.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-03-29-modular-monolith-refactor-design.md docs/plans/2026-03-29-modular-monolith-refactor.md src/asr_ol/modules src/asr_ol/bootstrap src/asr_ol/shared tests/architecture/test_module_layout.py
git commit -m "feat: add modular monolith skeleton and public entrypoints"
```

### Task 2: 建立架构依赖测试

**Files:**
- Create: `tests/architecture/test_module_dependencies.py`
- Modify: `pyproject.toml`

**Step 1: Write the failing test**

```python
def test_domain_layers_do_not_import_infrastructure_modules() -> None:
    violations = find_import_violations()
    assert violations == []
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_module_dependencies.py -q`
Expected: FAIL until scanner and allowlist are implemented

**Step 3: Write minimal implementation**

- 使用 `ast` 扫描 `src/asr_ol/modules/`
- 先固化阶段 1 规则：
  - 模块之间只能 import 对方 `public`
  - `shared` 不能 import `modules`
  - `bootstrap` 不受上述规则限制

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/architecture/test_module_dependencies.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/architecture/test_module_dependencies.py pyproject.toml
git commit -m "test: enforce module dependency rules"
```

### Task 3: 迁移 storage 到新模块

**Files:**
- Create: `src/asr_ol/modules/storage/application/store.py`
- Create: `src/asr_ol/modules/storage/infrastructure/sqlite_storage_worker.py`
- Modify: `src/asr_ol/modules/storage/public.py`
- Modify: `src/asr_ol/services/runtime_app.py`
- Test: `tests/unit/modules/storage/test_public_api.py`
- Test: `tests/integration/test_storage_worker.py`

**Step 1: Write the failing test**

```python
def test_storage_module_accepts_transcript_and_capture_records() -> None:
    module = build_storage_module(...)
    module.store_transcript(event)
    module.store_capture(capture)
    assert module
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/storage/test_public_api.py -q`
Expected: FAIL with missing builder or methods

**Step 3: Write minimal implementation**

- 复用现有 `StorageWorker`
- 通过新 `StorageModule` 包一层公开 API
- 现有 runtime 改从 `modules.storage.public` 取公开构建入口

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/storage/test_public_api.py tests/integration/test_storage_worker.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/modules/storage src/asr_ol/services/runtime_app.py tests/unit/modules/storage/test_public_api.py tests/integration/test_storage_worker.py
git commit -m "refactor: move storage behind module public api"
```

### Task 4: 迁移 injection 到新模块

**Files:**
- Create: `src/asr_ol/modules/injection/application/execute_capture.py`
- Create: `src/asr_ol/modules/injection/infrastructure/injector_worker.py`
- Create: `src/asr_ol/modules/injection/infrastructure/xdotool_injector.py`
- Create: `src/asr_ol/modules/injection/infrastructure/ydotool_injector.py`
- Modify: `src/asr_ol/modules/injection/public.py`
- Modify: `src/asr_ol/services/runtime_app.py`
- Test: `tests/unit/modules/injection/test_public_api.py`
- Test: `tests/unit/modules/injection/test_injector_worker_actions.py`

**Step 1: Write the failing test**

```python
def test_injection_module_executes_capture_completed() -> None:
    module = build_injection_module(...)
    assert module.execute_capture(capture_event) is True
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/injection/test_public_api.py -q`
Expected: FAIL with missing module public API

**Step 3: Write minimal implementation**

- 将注入动作执行能力封装到新模块
- `runtime` 改依赖 `modules.injection.public`

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/injection/test_public_api.py tests/unit/modules/injection/test_injector_worker_actions.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/modules/injection src/asr_ol/services/runtime_app.py tests/unit/modules/injection/test_public_api.py tests/unit/modules/injection/test_injector_worker_actions.py
git commit -m "refactor: move injection behind module public api"
```

### Task 5: 迁移 capture 到新模块

**Files:**
- Create: `src/asr_ol/modules/capture/domain/capture_fsm.py`
- Create: `src/asr_ol/modules/capture/application/capture_service.py`
- Create: `src/asr_ol/modules/capture/infrastructure/capture_worker.py`
- Modify: `src/asr_ol/modules/capture/public.py`
- Modify: `src/asr_ol/services/runtime_app.py`
- Test: `tests/unit/modules/capture/test_public_api.py`
- Test: `tests/unit/modules/capture/test_capture_fsm.py`
- Test: `tests/unit/modules/capture/test_capture_worker_routing.py`

**Step 1: Write the failing test**

```python
def test_capture_module_emits_capture_completed() -> None:
    events = []
    module = build_capture_module(...)
    module.subscribe_capture_completed(events.append)
    ...
    assert events
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/capture/test_public_api.py -q`
Expected: FAIL until public API and event output exist

**Step 3: Write minimal implementation**

- 将 `capture_fsm` 与提取逻辑迁入新模块
- 暴露 `accept_wake / accept_vad / accept_transcript / subscribe_capture_completed`

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/capture/test_public_api.py tests/unit/modules/capture/test_capture_fsm.py tests/unit/modules/capture/test_capture_worker_routing.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/modules/capture src/asr_ol/services/runtime_app.py tests/unit/modules/capture/test_public_api.py tests/unit/modules/capture/test_capture_fsm.py tests/unit/modules/capture/test_capture_worker_routing.py
git commit -m "refactor: move capture behind module public api"
```

### Task 6: 迁移 transcription 到新模块

**Files:**
- Create: `src/asr_ol/modules/transcription/application/transcription_service.py`
- Create: `src/asr_ol/modules/transcription/infrastructure/funasr_ws.py`
- Create: `src/asr_ol/modules/transcription/infrastructure/asr_worker.py`
- Modify: `src/asr_ol/modules/transcription/public.py`
- Modify: `src/asr_ol/services/runtime_app.py`
- Test: `tests/unit/modules/transcription/test_public_api.py`
- Test: `tests/unit/modules/transcription/test_funasr_ws.py`
- Test: `tests/unit/modules/transcription/test_asr_worker.py`

**Step 1: Write the failing test**

```python
def test_transcription_module_emits_transcript_finalized() -> None:
    seen = []
    module = build_transcription_module(...)
    module.subscribe_transcript_finalized(seen.append)
    ...
    assert seen
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_public_api.py -q`
Expected: FAIL with missing subscription path

**Step 3: Write minimal implementation**

- 将 `FunAsrWsEngine` 与 `AsrWorker` 收敛到新模块
- 暴露 `submit_audio` 与 `subscribe_transcript_finalized`

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_public_api.py tests/unit/modules/transcription/test_funasr_ws.py tests/unit/modules/transcription/test_asr_worker.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/modules/transcription src/asr_ol/services/runtime_app.py tests/unit/modules/transcription/test_public_api.py tests/unit/modules/transcription/test_funasr_ws.py tests/unit/modules/transcription/test_asr_worker.py
git commit -m "refactor: move transcription behind module public api"
```

### Task 7: 收口 bootstrap 并删除旧主边界

**Files:**
- Modify: `src/asr_ol/bootstrap/runtime_app.py`
- Modify: `src/asr_ol/cli/main.py`
- Modify: `src/asr_ol/api/runtime_status.py`
- Delete: `src/asr_ol/services/runtime_app.py`
- Delete: obsolete old-path wrappers after migration
- Test: `tests/unit/bootstrap/test_runtime_app.py`
- Test: `tests/unit/api/test_runtime_status.py`
- Test: `tests/e2e/test_cli_help.py`

**Step 1: Write the failing test**

```python
def test_cli_uses_bootstrap_runtime_app() -> None:
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py tests/e2e/test_cli_help.py -q`
Expected: FAIL until imports move to bootstrap path

**Step 3: Write minimal implementation**

- `cli` 与 API 统一依赖 `bootstrap/` 与模块 public API
- 删除旧主边界目录中的重复装配职责

**Step 4: Run test to verify it passes**

Run: `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py tests/unit/api/test_runtime_status.py tests/e2e/test_cli_help.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/bootstrap src/asr_ol/cli/main.py src/asr_ol/api/runtime_status.py tests/unit/bootstrap/test_runtime_app.py tests/unit/api/test_runtime_status.py tests/e2e/test_cli_help.py
git commit -m "refactor: centralize runtime composition in bootstrap"
```

### Task 8: 完整验证与文档收口

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-02-20-project-onboarding-map.md`

**Step 1: Run full verification**

Run: `uv run --python 3.11 python -m pytest -q`
Expected: PASS

Run: `uv run --python 3.11 ruff check src tests`
Expected: PASS

Run: `uv run --python 3.11 python -m asr_ol --help`
Expected: exit code 0 and CLI help text

**Step 2: Update docs**

- 更新 onboarding 文档中的目录和装配路径
- 记录模块边界与导入规则

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-02-20-project-onboarding-map.md
git commit -m "docs: document modular monolith architecture"
```
