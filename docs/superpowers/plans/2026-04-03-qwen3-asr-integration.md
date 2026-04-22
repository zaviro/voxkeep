# Qwen3-ASR-0.6B Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the FunASR-bound transcription path with a backend-oriented transcription module that can consume an externally managed `Qwen3-ASR-0.6B` `vLLM` streaming service while keeping VoxKeep's public runtime behavior final-only in phase 1.

**Architecture:** Keep the public `modules/transcription` API stable, add an internal backend-neutral engine seam plus normalized transcript event model, implement a dedicated `qwen_vllm` adapter, then extend config and backend registry so runtime selection is explicit and non-silent. Preserve the existing `capture` contract and final-only storage behavior.

**Tech Stack:** Python 3.11, `uv`, pytest, existing threaded queue runtime, `websockets`/HTTP streaming client used by the current runtime dependencies, Ruff, Pyright

---

### Task 1: Add A Backend-Neutral Transcription Engine Seam

**Files:**
- Create: `src/voxkeep/modules/transcription/application/backend_events.py`
- Create: `src/voxkeep/modules/transcription/infrastructure/engine_factory.py`
- Modify: `src/voxkeep/modules/transcription/contracts.py`
- Modify: `src/voxkeep/modules/transcription/infrastructure/funasr_ws.py`
- Modify: `src/voxkeep/modules/transcription/public.py`
- Modify: `tests/unit/modules/transcription/test_transcription_public_api.py`

- [ ] **Step 1: Write the failing tests for backend selection and normalized engine output**

```python
from __future__ import annotations

import queue
import threading

from voxkeep.shared.events import AsrFinalEvent
from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.modules.transcription.infrastructure.engine_factory import build_asr_engine
from voxkeep.modules.transcription.public import build_transcription_module


class _FakeEngine:
    def __init__(self) -> None:
        self.final_queue: queue.Queue[BackendTranscriptEvent] = queue.Queue()


def test_build_transcription_module_uses_engine_factory(monkeypatch, app_config) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=threading.Event(),
        cfg=app_config,
    )
    assert module is not None


def test_build_asr_engine_rejects_unknown_backend(app_config) -> None:
    bad_cfg = app_config.__class__(**{**app_config.__dict__, "asr_backend": "missing"})
    with pytest.raises(ValueError, match="unsupported asr backend"):
        build_asr_engine(cfg=bad_cfg, stop_event=threading.Event())
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_transcription_public_api.py -q`

Expected: FAIL because `build_asr_engine` and `BackendTranscriptEvent` do not exist yet, and `public.py` still hardcodes `FunAsrWsEngine`.

- [ ] **Step 3: Add the backend-neutral event model and engine factory**

```python
# src/voxkeep/modules/transcription/application/backend_events.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class BackendTranscriptEvent:
    segment_id: str
    text: str
    start_ts: float
    end_ts: float
    event_type: Literal["partial", "final"]

    @property
    def is_final(self) -> bool:
        return self.event_type == "final"
```

```python
# src/voxkeep/modules/transcription/infrastructure/engine_factory.py
from __future__ import annotations

import threading

from voxkeep.shared.config import AppConfig
from voxkeep.modules.transcription.contracts import TranscriptionEngine
from voxkeep.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine


def build_asr_engine(*, cfg: AppConfig, stop_event: threading.Event) -> TranscriptionEngine:
    if cfg.asr_backend == "funasr_ws_external":
        return FunAsrWsEngine(cfg=cfg, stop_event=stop_event)
    raise ValueError(f"unsupported asr backend for transcription engine: {cfg.asr_backend}")
```

```python
# src/voxkeep/modules/transcription/contracts.py
from __future__ import annotations

import queue
from typing import Protocol

from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.shared.events import ProcessedFrame
from voxkeep.shared.types import TranscriptFinalized


class TranscriptionEngine(Protocol):
    @property
    def final_queue(self) -> queue.Queue[BackendTranscriptEvent]:
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def submit_frame(self, frame: ProcessedFrame) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
```

```python
# src/voxkeep/modules/transcription/public.py
import queue
import threading

from voxkeep.shared.config import AppConfig
from voxkeep.shared.events import AsrFinalEvent, ProcessedFrame, StorageRecord
from voxkeep.modules.transcription.infrastructure.engine_factory import build_asr_engine

class WorkerTranscriptionModule:
    def __init__(
        self,
        *,
        capture_queue: queue.Queue[AsrFinalEvent],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        cfg: AppConfig,
        in_queue: queue.Queue[ProcessedFrame] | None = None,
    ) -> None:
        self._engine = build_asr_engine(cfg=cfg, stop_event=stop_event)
        self._final_in_queue = self._engine.final_queue
```

- [ ] **Step 4: Expand the public transcription tests to patch the factory instead of `FunAsrWsEngine`**

```python
monkeypatch.setattr(
    "voxkeep.modules.transcription.public.build_asr_engine",
    lambda cfg, stop_event: fake_engine,
)
```

Also change the fake engine shape used in tests so it exposes:

```python
self.final_queue: queue.Queue[AsrFinalEvent] = queue.Queue()
```

This preserves the current public behavior while moving construction through a backend seam.

- [ ] **Step 5: Run the tests to verify the seam works**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_transcription_public_api.py -q`

Expected: PASS

- [ ] **Step 6: Commit the seam extraction**

```bash
git add src/voxkeep/modules/transcription/application/backend_events.py \
  src/voxkeep/modules/transcription/contracts.py \
  src/voxkeep/modules/transcription/infrastructure/engine_factory.py \
  src/voxkeep/modules/transcription/infrastructure/funasr_ws.py \
  src/voxkeep/modules/transcription/public.py \
  tests/unit/modules/transcription/test_transcription_public_api.py
git commit -m "refactor: add backend-neutral transcription engine seam"
```

### Task 2: Normalize Engine Events And Keep Final-Only Public Semantics

**Files:**
- Modify: `src/voxkeep/modules/transcription/infrastructure/asr_worker.py`
- Modify: `src/voxkeep/modules/transcription/application/transcription_service.py`
- Modify: `tests/unit/modules/transcription/test_asr_worker.py`
- Modify: `tests/unit/modules/transcription/test_transcription_public_api.py`

- [ ] **Step 1: Write failing tests for final-only fanout from normalized backend events**

```python
from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent


def _backend_event(*, text: str = "hello", event_type: str = "final") -> BackendTranscriptEvent:
    return BackendTranscriptEvent(
        segment_id="seg-1",
        text=text,
        start_ts=1.0,
        end_ts=1.1,
        event_type=event_type,
    )


def test_drain_backend_events_ignores_partial_events() -> None:
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    final_q.put(_backend_event(event_type="partial"))
    worker = AsrWorker(
        in_queue=queue.Queue(),
        final_in_queue=final_q,
        out_queue=queue.Queue(),
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=threading.Event(),
        engine=types.SimpleNamespace(start=lambda: None, submit_frame=lambda frame: None, close=lambda: None),
        store_final_only=True,
    )
    worker._drain_final_events()
    assert worker._out_queue.empty()
    assert worker._capture_queue.empty()
    assert worker._storage_queue.empty()
```

- [ ] **Step 2: Run the worker tests to verify they fail**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_asr_worker.py -q`

Expected: FAIL because the worker still consumes `AsrFinalEvent` directly and has no normalized backend event handling.

- [ ] **Step 3: Update the shared engine contract and worker input type**

```python
# src/voxkeep/modules/transcription/infrastructure/asr_worker.py
from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent

class AsrWorker:
    def __init__(
        self,
        *,
        in_queue: queue.Queue[ProcessedFrame],
        final_in_queue: queue.Queue[BackendTranscriptEvent],
        out_queue: queue.Queue[AsrFinalEvent],
        capture_queue: queue.Queue[AsrFinalEvent],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        engine: TranscriptionEngine,
        store_final_only: bool,
    ) -> None:
        self._final_in_queue = final_in_queue

    def _drain_final_events(self) -> None:
        while True:
            try:
                event = self._final_in_queue.get_nowait()
            except queue.Empty:
                return
            if not event.is_final:
                continue
            normalized = AsrFinalEvent(
                segment_id=event.segment_id,
                text=event.text,
                start_ts=event.start_ts,
                end_ts=event.end_ts,
                is_final=True,
            )
```

Use the existing storage/capture fanout path after normalization so `capture` and storage remain unchanged.

- [ ] **Step 4: Keep the public conversion helpers simple**

```python
# src/voxkeep/modules/transcription/application/transcription_service.py
def to_transcript_finalized(event: AsrFinalEvent) -> TranscriptFinalized:
    return TranscriptFinalized(
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        is_final=event.is_final,
    )
```

Do not expose partial events in this task.

- [ ] **Step 5: Run the transcription unit tests**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_asr_worker.py tests/unit/modules/transcription/test_transcription_public_api.py -q`

Expected: PASS

- [ ] **Step 6: Commit the event normalization**

```bash
git add src/voxkeep/modules/transcription/infrastructure/asr_worker.py \
  src/voxkeep/modules/transcription/application/transcription_service.py \
  tests/unit/modules/transcription/test_asr_worker.py \
  tests/unit/modules/transcription/test_transcription_public_api.py
git commit -m "refactor: normalize transcription backend events"
```

### Task 3: Add The `qwen_vllm` Backend Registry And Config Surface

**Files:**
- Modify: `src/voxkeep/shared/asr_backends.py`
- Modify: `src/voxkeep/shared/config_defaults.py`
- Modify: `src/voxkeep/shared/config_env.py`
- Modify: `src/voxkeep/shared/config_loader.py`
- Modify: `src/voxkeep/shared/config_schema.py`
- Modify: `tests/unit/shared/test_asr_backends.py`
- Modify: `tests/unit/shared/test_config.py`
- Modify: `tests/conftest.py`
- Modify: `config/config.yaml`

- [ ] **Step 1: Write failing tests for `qwen_vllm` backend registration and config loading**

```python
def test_builtin_registry_contains_qwen_vllm() -> None:
    backend = resolve_backend_definition("qwen_vllm")
    assert backend.transport == "streaming_http"
    assert backend.kind == "external_service"


def test_load_config_supports_qwen_backend(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\\n"
        "  backend: qwen_vllm\\n"
        "  external:\\n"
        "    host: 127.0.0.1\\n"
        "    port: 8000\\n"
        "    path: /v1/audio/transcriptions\\n"
        "    use_ssl: false\\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.asr_backend == "qwen_vllm"
    assert cfg.asr_external_port == 8000
```

- [ ] **Step 2: Run the shared config tests to verify they fail**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_backends.py tests/unit/shared/test_config.py -q`

Expected: FAIL because the backend registry and config defaults do not know `qwen_vllm`.

- [ ] **Step 3: Register `qwen_vllm` and set conservative external-service defaults**

```python
# src/voxkeep/shared/asr_backends.py
"qwen_vllm": AsrBackendDefinition(
    backend_id="qwen_vllm",
    display_name="Qwen3-ASR vLLM External",
    kind="external_service",
    transport="streaming_http",
),
```

```python
# src/voxkeep/shared/config_defaults.py
"asr": {
    "backend": "funasr_ws_external",
    "mode": "external",
    "external": {
        "host": "127.0.0.1",
        "port": 10096,
        "path": "/",
        "use_ssl": False,
    },
    "managed": {
        "provider": "docker",
        "image": "registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13",
        "service_name": "funasr",
        "expose_port": 10096,
        "models_dir": "~/.local/share/voxkeep/models/funasr",
    },
},
```

Keep the checked-in default backend as `funasr_ws_external` in this task to reduce migration blast radius; only the registry and config model gain first-class `qwen_vllm` support.

- [ ] **Step 4: Load reconnect settings through neutral ASR fields while preserving the legacy `funasr` section**

Use the existing `funasr.reconnect_*` values as the compatibility source for this phase, but make the schema and comments in `config/config.yaml` explicit that reconnect policy now applies to external ASR services generally.

```python
# src/voxkeep/shared/config_loader.py
funasr = merged.get("funasr", {})
asr_runtime = asr.get("runtime", {})
reconnect_initial = asr_runtime.get("reconnect_initial_s", funasr["reconnect_initial_s"])
reconnect_max = asr_runtime.get("reconnect_max_s", funasr["reconnect_max_s"])
```

- [ ] **Step 5: Update the example config and fixtures**

In `config/config.yaml`, add explicit `asr.backend` and `asr.external` comments/examples for the future Qwen path while keeping the current sample runnable:

```yaml
asr:
  backend: funasr_ws_external
  mode: external
  external:
    host: 127.0.0.1
    port: 10096
    path: /
    use_ssl: false
```

In `tests/conftest.py`, add a reusable `AppConfig` fixture variant or direct fields covering:

```python
asr_backend="qwen_vllm",
asr_external_host="127.0.0.1",
asr_external_port=8000,
asr_external_path="/v1/audio/transcriptions",
asr_external_use_ssl=False,
```

- [ ] **Step 6: Run the shared config tests**

Run: `uv run --python 3.11 python -m pytest tests/unit/shared/test_asr_backends.py tests/unit/shared/test_config.py -q`

Expected: PASS

- [ ] **Step 7: Commit the backend/config groundwork**

```bash
git add src/voxkeep/shared/asr_backends.py \
  src/voxkeep/shared/config_defaults.py \
  src/voxkeep/shared/config_env.py \
  src/voxkeep/shared/config_loader.py \
  src/voxkeep/shared/config_schema.py \
  tests/unit/shared/test_asr_backends.py \
  tests/unit/shared/test_config.py \
  tests/conftest.py \
  config/config.yaml
git commit -m "feat: add qwen vllm backend configuration support"
```

### Task 4: Implement The Qwen `vLLM` Streaming Adapter

**Files:**
- Create: `src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py`
- Modify: `src/voxkeep/modules/transcription/infrastructure/engine_factory.py`
- Modify: `src/voxkeep/modules/transcription/public.py`
- Create: `tests/unit/modules/transcription/test_qwen_vllm.py`
- Modify: `tests/unit/modules/transcription/test_transcription_public_api.py`

- [ ] **Step 1: Write failing adapter tests for payload parsing and final-only queue output**

```python
from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.modules.transcription.infrastructure.qwen_vllm import QwenVllmEngine


def test_parse_stream_event_maps_final_transcript(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())
    payload = {
        "type": "transcript",
        "delta": {"text": "hello world"},
        "finish_reason": "stop",
        "start": 1.0,
        "end": 1.2,
        "segment_id": "seg-1",
    }
    event = engine._parse_stream_event(payload)
    assert event == BackendTranscriptEvent(
        segment_id="seg-1",
        text="hello world",
        start_ts=1.0,
        end_ts=1.2,
        event_type="final",
    )


def test_receiver_discards_partial_events(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())
    partial = {
        "type": "transcript",
        "delta": {"text": "hel"},
        "finish_reason": None,
        "start": 1.0,
        "end": 1.1,
        "segment_id": "seg-1",
    }
    assert engine._parse_stream_event(partial) is None
    assert engine.final_queue.empty()
```

- [ ] **Step 2: Run the new adapter tests to verify they fail**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_qwen_vllm.py -q`

Expected: FAIL because the adapter does not exist yet.

- [ ] **Step 3: Implement the adapter with explicit responsibilities**

```python
# src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py
class QwenVllmEngine(TranscriptionEngine):
    def __init__(self, cfg: AppConfig, stop_event: threading.Event) -> None:
        self._cfg = cfg
        self._stop_event = stop_event
        self._in_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self._final_queue: queue.Queue[BackendTranscriptEvent] = queue.Queue(
            maxsize=cfg.max_queue_size
        )

    @property
    def final_queue(self) -> queue.Queue[BackendTranscriptEvent]:
        return self._final_queue
```

Implement these methods and keep them small:

- `_run()`
- `_run_session()`
- `_sender()` or request body builder for the chosen streaming transport
- `_receiver()`
- `_parse_stream_event()`

Behavior requirements:

- connect to the protocol-specific external endpoint derived from config
- submit buffered audio frames in order
- only enqueue normalized `BackendTranscriptEvent` values with concrete fields copied from the backend payload and `event_type="final"`
- ignore empty text and partial events
- log connection/reconnect failures with backend id and endpoint

- [ ] **Step 4: Register `qwen_vllm` in the engine factory**

```python
from voxkeep.modules.transcription.infrastructure.qwen_vllm import QwenVllmEngine


def build_asr_engine(*, cfg: AppConfig, stop_event: threading.Event) -> TranscriptionEngine:
    if cfg.asr_backend == "qwen_vllm":
        return QwenVllmEngine(cfg=cfg, stop_event=stop_event)
    if cfg.asr_backend == "funasr_ws_external":
        return FunAsrWsEngine(cfg=cfg, stop_event=stop_event)
    raise ValueError(f"unsupported asr backend for transcription engine: {cfg.asr_backend}")
```

- [ ] **Step 5: Update the public transcription tests to prove the new backend can be selected**

Add one focused test:

```python
def test_build_transcription_module_supports_qwen_backend(monkeypatch, app_config) -> None:
    cfg = replace(app_config, asr_backend="qwen_vllm")
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=threading.Event(),
        cfg=cfg,
    )
    assert module is not None
```

- [ ] **Step 6: Run the transcription adapter tests**

Run: `uv run --python 3.11 python -m pytest tests/unit/modules/transcription/test_qwen_vllm.py tests/unit/modules/transcription/test_transcription_public_api.py tests/unit/modules/transcription/test_asr_worker.py -q`

Expected: PASS

- [ ] **Step 7: Commit the Qwen adapter**

```bash
git add src/voxkeep/modules/transcription/infrastructure/qwen_vllm.py \
  src/voxkeep/modules/transcription/infrastructure/engine_factory.py \
  src/voxkeep/modules/transcription/public.py \
  tests/unit/modules/transcription/test_qwen_vllm.py \
  tests/unit/modules/transcription/test_transcription_public_api.py
git commit -m "feat: add qwen vllm transcription adapter"
```

### Task 5: Validate Runtime Wiring, Logging, And Documentation

**Files:**
- Modify: `tests/unit/bootstrap/test_runtime_app.py`
- Modify: `tests/architecture/test_module_layout.py`
- Modify: `docs/superpowers/specs/2026-04-03-qwen3-asr-design.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write a focused runtime wiring regression test**

```python
def test_runtime_builds_qwen_transcription_backend_through_public_api(
    monkeypatch, app_config
) -> None:
    built = {}

    def _build_transcription_module(**kwargs):
        built["cfg"] = kwargs["cfg"]
        return _FakeTranscriptionModule()

    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        _build_transcription_module,
    )
    runtime = build_runtime(cfg=replace(app_config, asr_backend="qwen_vllm"))
    assert built["cfg"].asr_backend == "qwen_vllm"
```

- [ ] **Step 2: Run the bootstrap and architecture tests to verify no boundary regression**

Run: `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py tests/architecture -q`

Expected: PASS

- [ ] **Step 3: Update operator-facing docs**

Add a short section to `AGENTS.md` documenting the new preferred path:

```md
- Preferred long-term ASR path is `qwen_vllm` against an externally managed local service.
- VoxKeep should not start or stop the Qwen `vLLM` service.
- Before diagnosing Qwen runtime failures, validate the external ASR endpoint separately from VoxKeep.
```

Update the spec if implementation details changed while building the adapter, but keep the architectural intent stable.

- [ ] **Step 4: Run the fast verification bundle**

Run:

```bash
make fmt
make lint
make typecheck
make test-fast
uv run --python 3.11 python -m pytest \
  tests/unit/modules/transcription/test_qwen_vllm.py \
  tests/unit/modules/transcription/test_transcription_public_api.py \
  tests/unit/shared/test_asr_backends.py \
  tests/unit/shared/test_config.py \
  tests/unit/bootstrap/test_runtime_app.py -q
```

Expected:

- formatter makes no further changes after rerun
- lint passes
- typecheck passes, or any failure is clearly identified as a missing optional runtime dependency rather than a regression
- focused tests pass

- [ ] **Step 5: Commit the final wiring and docs update**

```bash
git add tests/unit/bootstrap/test_runtime_app.py \
  tests/architecture/test_module_layout.py \
  docs/superpowers/specs/2026-04-03-qwen3-asr-design.md \
  AGENTS.md
git commit -m "docs: document qwen vllm as preferred asr path"
```

## Self-Review

### Spec Coverage

- Backend-neutral transcription boundary: covered by Tasks 1 and 2
- Dedicated `qwen_vllm` adapter: covered by Task 4
- Explicit backend/config selection: covered by Task 3
- Final-only public semantics in phase 1: covered by Tasks 2 and 4
- Runtime/documentation/acceptance path: covered by Task 5

### Placeholder Scan

- No `TODO`, `TBD`, or “implement later” markers remain in the task steps
- Each task includes exact file targets, commands, and commit messages

### Type Consistency

- Internal adapter output type is `BackendTranscriptEvent`
- Public runtime output type remains `TranscriptFinalized`
- Existing downstream capture/storage path continues to normalize through `AsrFinalEvent`
