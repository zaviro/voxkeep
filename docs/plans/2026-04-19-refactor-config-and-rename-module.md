# Refactor: Config Decomposition and Audio Engine Rename Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Clean up the architectural boundaries by decomposing the flat `AppConfig` into module-specific sub-configs and renaming the confusingly named `runtime` module to `audio_engine`.

**Architecture:**
1. **Config Decomposition**: Introduce nested dataclasses in `config_schema.py` and update the loader to populate them. Refactor all module `public.py` entrypoints to accept their specific sub-config instead of the global `AppConfig`.
2. **Audio Engine Rename**: Use `git mv` to rename `src/voxkeep/modules/runtime/` to `audio_engine/` and update all imports and test paths.

**Tech Stack:** Python 3.11, `dataclasses`, `uv`.

---

### Task 1: Define Sub-Dataclasses in `config_schema.py`

**Files:**
- Modify: `src/voxkeep/shared/config_schema.py`

**Step 1: Define sub-dataclasses**

Move fields from `AppConfig` into new sub-dataclasses: `AudioEngineConfig`, `AsrConfig`, `CaptureConfig`, `StorageConfig`, `InjectorConfig`.

```python
@dataclass(slots=True, frozen=True)
class AudioEngineConfig:
    sample_rate: int
    channels: int
    frame_ms: int
    max_queue_size: int

@dataclass(slots=True, frozen=True)
class AsrConfig:
    backend: str
    mode: str
    external_host: str
    external_port: int
    external_path: str
    use_ssl: bool
    reconnect_initial_s: float
    reconnect_max_s: float
    runtime_reconnect_initial_s: float
    runtime_reconnect_max_s: float
    qwen_model: str
    qwen_realtime: bool
    qwen_gpu_memory_utilization: float
    qwen_max_model_len: int

@dataclass(slots=True, frozen=True)
class CaptureConfig:
    wake_threshold: float
    wake_rules: tuple[WakeRuleConfig, ...]
    vad_speech_threshold: float
    vad_silence_ms: int
    pre_roll_ms: int
    armed_timeout_ms: int
    max_queue_size: int

@dataclass(slots=True, frozen=True)
class StorageConfig:
    sqlite_path: str
    store_final_only: bool
    jsonl_debug_path: str | None
    max_queue_size: int

@dataclass(slots=True, frozen=True)
class InjectorConfig:
    backend: str
    auto_enter: bool
    xdotool_delay_ms: int
    openclaw_command: tuple[str, ...]
    openclaw_timeout_s: float
    max_queue_size: int
```

**Step 2: Update `AppConfig` to use these sub-dataclasses**

```python
@dataclass(slots=True, frozen=True)
class AppConfig:
    audio_engine: AudioEngineConfig
    asr: AsrConfig
    capture: CaptureConfig
    storage: StorageConfig
    injector: InjectorConfig
    log_level: str
```

**Step 3: Update `AppConfig.__post_init__` and properties**

Adapt validation and properties (like `frame_samples`, `asr_ws_url`) to work with the new nested structure.

**Step 4: Run configuration unit tests**

Run: `make test-unit` (focus on `tests/unit/shared/test_config.py`)
Expected: Failures (due to loader and tests still using the flat structure).

**Step 5: Commit**

```bash
git add src/voxkeep/shared/config_schema.py
git commit -m "refactor: define nested sub-configs in config_schema"
```

---

### Task 2: Update `config_loader.py` to Populate Nested Config

**Files:**
- Modify: `src/voxkeep/shared/config_loader.py`

**Step 1: Update `load_config` implementation**

Populate the sub-dataclasses from the merged configuration dictionary.

**Step 2: Run configuration tests**

Run: `make test-unit`
Expected: Fewer failures, but many tests will still fail because they expect a flat `AppConfig` or use old attribute names.

**Step 3: Commit**

```bash
git add src/voxkeep/shared/config_loader.py
git commit -m "refactor: update config_loader to populate nested AppConfig"
```

---

### Task 3: Update Module Entry Points (Public APIs)

**Files:**
- Modify: `src/voxkeep/modules/capture/public.py`
- Modify: `src/voxkeep/modules/injection/public.py`
- Modify: `src/voxkeep/modules/storage/public.py`
- Modify: `src/voxkeep/modules/transcription/public.py`

**Step 1: Update `build_*` functions to accept sub-configs**

Example for capture:
```python
def build_capture_module(
    *,
    downstream_queue: queue.Queue[CaptureCommand],
    storage_queue: queue.Queue[StorageRecord],
    stop_event: threading.Event,
    cfg: CaptureConfig,  # Changed from AppConfig
    ...
) -> CaptureModule:
```

**Step 2: Update internal module calls to use the sub-config**

**Step 3: Commit**

```bash
git add src/voxkeep/modules/*/public.py
git commit -m "refactor: update module public APIs to use sub-configs"
```

---

### Task 4: Update `AppRuntime` and Tests

**Files:**
- Modify: `src/voxkeep/bootstrap/runtime_app.py`
- Modify: `tests/conftest.py`
- Modify: Many test files identified in `grep` search.

**Step 1: Update `AppRuntime.__init__`**

Pass `cfg.audio_engine`, `cfg.asr`, etc., to the respective module builders.

**Step 2: Update `tests/conftest.py`**

Update the `app_config` fixture to return the nested structure.

**Step 3: Fix all remaining test failures**

Iteratively run `make test` and fix attribute access (e.g., `cfg.sample_rate` -> `cfg.audio_engine.sample_rate`).

**Step 4: Commit**

```bash
git add src/voxkeep/bootstrap/runtime_app.py tests/
git commit -m "refactor: update runtime_app and tests for nested config"
```

---

### Task 5: Rename `runtime` module to `audio_engine`

**Files:**
- Rename: `src/voxkeep/modules/runtime/` -> `src/voxkeep/modules/audio_engine/`
- Modify: `src/voxkeep/bootstrap/runtime_app.py`
- Modify: `src/voxkeep/shared/config_schema.py`
- Modify: `tests/unit/modules/runtime/` -> `tests/unit/modules/audio_engine/`

**Step 1: Perform git mv**

```bash
git mv src/voxkeep/modules/runtime src/voxkeep/modules/audio_engine
git mv tests/unit/modules/runtime tests/unit/modules/audio_engine
```

**Step 2: Update import statements**

Replace `from voxkeep.modules.runtime` with `from voxkeep.modules.audio_engine`.

**Step 3: Update `AppConfig` and `AudioEngineConfig` field names if necessary**

(Already done in Task 1, but check for consistency).

**Step 4: Run all tests**

Run: `make test && make test-architecture`
Expected: PASS

**Step 5: Commit**

```bash
git add .
git commit -m "refactor: rename runtime module to audio_engine"
```
