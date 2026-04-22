# Design Doc: Module-Centric Config Decomposition

## 1. Problem Statement
The current `AppConfig` is a flat, oversized dataclass. Every module receives the entire configuration object, even though they only need a small subset of fields. This creates unnecessary coupling and makes module interfaces less explicit.

## 2. Proposed Solution
Decompose `AppConfig` into nested dataclasses aligned with module boundaries in `src/voxkeep/modules/`.

### 2.1 Proposed Structure
```python
@dataclass(frozen=True)
class AudioEngineConfig:
    sample_rate: int
    channels: int
    frame_ms: int
    max_queue_size: int

@dataclass(frozen=True)
class AsrConfig:
    backend: str
    external_host: str
    external_port: int
    external_path: str
    use_ssl: bool
    reconnect_initial_s: float
    reconnect_max_s: float
    qwen_model: str
    qwen_realtime: bool
    # ... other ASR specific fields

@dataclass(frozen=True)
class AppConfig:
    audio_engine: AudioEngineConfig
    asr: AsrConfig
    capture: CaptureConfig
    storage: StorageConfig
    injector: InjectorConfig
    log_level: str
```

### 2.2 Implementation Strategy
1.  **Refactor `config_schema.py`**: Define sub-dataclasses first, then update `AppConfig`.
2.  **Update `config_loader.py`**: Adjust the mapping logic to populate the nested structure.
3.  **Update Module Entry Points**: Change functions like `build_capture_module(cfg: AppConfig)` to `build_capture_module(cfg: CaptureConfig)`.
4.  **Verify**: Ensure all tests (especially architecture tests) pass.

## 3. Success Criteria
- Each module only has access to its relevant configuration subset.
- `AppConfig` acts as a clean composition root for configuration.
