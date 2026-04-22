from __future__ import annotations

import asyncio
from dataclasses import replace
from importlib import import_module
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.modules.transcription.contracts import TranscriptionBackendEvent, TranscriptionEngine
from voxkeep.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine
from voxkeep.shared.events import AsrFinalEvent, StorageRecord
from voxkeep.modules.transcription.public import build_transcription_module
from voxkeep.shared.config import AppConfig
from voxkeep.shared.types import AudioFrame


class _FakeEngine:
    def __init__(self) -> None:
        self.final_queue: queue.Queue[TranscriptionBackendEvent] = queue.Queue()
        self.started = 0
        self.closed = 0
        self.joined = 0
        self.submitted = []

    def start(self) -> None:
        self.started += 1

    def submit_frame(self, frame) -> None:  # type: ignore[no-untyped-def]
        self.submitted.append(frame)

    def close(self) -> None:
        self.closed += 1

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        self.joined += 1


class _FakeWorker:
    def __init__(
        self,
        *,
        in_queue,
        final_in_queue,
        out_queue,
        capture_queue,
        storage_queue,
        stop_event,
        engine,
        store_final_only,
    ) -> None:
        _ = in_queue, out_queue, capture_queue, storage_queue, stop_event, engine, store_final_only
        self.final_in_queue = final_in_queue
        self.started = 0
        self.joined = []

    def start(self) -> None:
        self.started += 1

    def join(self, timeout: float | None = None) -> None:
        self.joined.append(timeout)

    def is_alive(self) -> bool:
        return False


def test_transcription_module_submits_audio_and_emits_public_events(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop_event = threading.Event()
    seen: list[str] = []

    module = build_transcription_module(
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop_event,
        asr_cfg=app_config.asr,
        storage_cfg=app_config.storage,
    )
    module.subscribe_transcript_finalized(lambda event: seen.append(event.text))
    module.start()
    module.submit_audio(
        AudioFrame(
            frame_id=1,
            data_int16=(b"\x00\x00" * 160),
            pcm_f32=np.zeros(160, dtype=np.float32),
            sample_rate=16000,
            ts_start=1.0,
            ts_end=1.01,
        )
    )
    fake_engine.final_queue.put(
        BackendTranscriptEvent(
            segment_id="seg-1",
            text="hello",
            start_ts=1.0,
            end_ts=1.2,
            event_type="final",
        )
    )

    deadline = time.time() + 2.0
    while time.time() < deadline and not seen:
        time.sleep(0.02)

    stop_event.set()
    module.join(timeout=2)

    assert len(fake_engine.submitted) == 1
    assert seen == ["hello"]
    assert fake_engine.joined == 1
    capture_event = capture_q.get_nowait()
    storage_event = storage_q.get_nowait()
    assert isinstance(capture_event, AsrFinalEvent)
    assert capture_event.text == "hello"
    assert isinstance(storage_event, StorageRecord)
    assert storage_event.text == "hello"


def test_transcription_module_ignores_non_final_backend_events(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop_event = threading.Event()
    seen: list[str] = []

    module = build_transcription_module(
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop_event,
        asr_cfg=app_config.asr,
        storage_cfg=app_config.storage,
    )
    module.subscribe_transcript_finalized(lambda event: seen.append(event.text))
    module.start()
    fake_engine.final_queue.put(
        BackendTranscriptEvent(
            segment_id="seg-1",
            text="partial text",
            start_ts=1.0,
            end_ts=1.1,
            event_type="partial",
        )
    )

    deadline = time.time() + 1.0
    while time.time() < deadline and not seen:
        time.sleep(0.02)

    stop_event.set()
    module.join(timeout=2)

    assert seen == []
    assert capture_q.empty()
    assert storage_q.empty()


def test_transcription_module_feeds_backend_events_into_worker(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    created_workers: list[_FakeWorker] = []

    def _fake_worker_factory(**kwargs):
        worker = _FakeWorker(**kwargs)
        created_workers.append(worker)
        return worker

    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.LegacyAsrWorker",
        _fake_worker_factory,
    )
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop_event = threading.Event()

    module = build_transcription_module(
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop_event,
        asr_cfg=app_config.asr,
        storage_cfg=app_config.storage,
    )
    module.start()
    fake_engine.final_queue.put(
        BackendTranscriptEvent(
            segment_id="seg-1",
            text="worker path",
            start_ts=1.0,
            end_ts=1.1,
            event_type="final",
        )
    )

    deadline = time.time() + 2.0
    while time.time() < deadline and created_workers and created_workers[0].final_in_queue.empty():
        time.sleep(0.02)

    stop_event.set()
    module.join(timeout=2)

    worker_event = created_workers[0].final_in_queue.get_nowait()
    assert isinstance(worker_event, BackendTranscriptEvent)
    assert worker_event.text == "worker path"


def test_transcription_module_bridge_skips_partial_events_before_worker_queue(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    created_workers: list[_FakeWorker] = []

    def _fake_worker_factory(**kwargs):
        worker = _FakeWorker(**kwargs)
        created_workers.append(worker)
        return worker

    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.LegacyAsrWorker",
        _fake_worker_factory,
    )
    stop_event = threading.Event()
    new_asr = replace(app_config.asr, max_queue_size=1)
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=stop_event,
        asr_cfg=new_asr,
        storage_cfg=app_config.storage,
    )
    module.start()

    fake_engine.final_queue.put(
        BackendTranscriptEvent(
            segment_id="seg-1",
            text="partial text",
            start_ts=1.0,
            end_ts=1.1,
            event_type="partial",
        )
    )
    fake_engine.final_queue.put(
        BackendTranscriptEvent(
            segment_id="seg-2",
            text="final text",
            start_ts=1.2,
            end_ts=1.3,
            event_type="final",
        )
    )

    deadline = time.time() + 2.0
    while time.time() < deadline and created_workers[0].final_in_queue.empty():
        time.sleep(0.02)

    stop_event.set()
    module.join(timeout=2)

    worker_event = created_workers[0].final_in_queue.get_nowait()
    assert worker_event.text == "final text"


def test_transcription_module_submit_audio_drops_when_queue_is_full(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    stop_event = threading.Event()
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=stop_event,
        asr_cfg=app_config.asr,
        storage_cfg=app_config.storage,
        in_queue=queue.Queue(maxsize=1),
    )
    frame = AudioFrame(
        frame_id=1,
        data_int16=(b"\x00\x00" * 160),
        pcm_f32=np.zeros(160, dtype=np.float32),
        sample_rate=16000,
        ts_start=1.0,
        ts_end=1.01,
    )

    module.submit_audio(frame)
    module.submit_audio(frame)

    assert fake_engine.submitted == []


def test_transcription_module_stop_sets_stop_event(monkeypatch, app_config: AppConfig) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )
    stop_event = threading.Event()
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=stop_event,
        asr_cfg=app_config.asr,
        storage_cfg=app_config.storage,
    )

    module.stop()

    assert stop_event.is_set() is True


def test_build_asr_engine_rejects_unknown_backend() -> None:
    engine_factory = import_module("voxkeep.modules.transcription.infrastructure.engine_factory")

    with pytest.raises(ValueError, match="unsupported asr backend"):
        engine_factory.build_asr_engine(
            cfg=SimpleNamespace(backend="missing"),
            stop_event=threading.Event(),
        )


def test_build_asr_engine_exposes_backend_dispatch_registry() -> None:
    engine_factory = import_module("voxkeep.modules.transcription.infrastructure.engine_factory")
    builders = getattr(engine_factory, "BACKEND_ENGINE_BUILDERS", None)

    assert builders is not None
    assert set(builders) >= {"qwen_vllm"}


def test_build_asr_engine_uses_backend_specific_constructor(
    monkeypatch, app_config: AppConfig
) -> None:
    engine_factory = import_module("voxkeep.modules.transcription.infrastructure.engine_factory")
    sentinel_external = object()
    sentinel_qwen = object()
    monkeypatch.setitem(
        engine_factory.BACKEND_ENGINE_BUILDERS, "funasr_ws_external", lambda **_: sentinel_external
    )
    monkeypatch.setitem(
        engine_factory.BACKEND_ENGINE_BUILDERS, "qwen_vllm", lambda **_: sentinel_qwen
    )

    # Note: funasr_ws_external was removed from BUILTIN_BACKENDS but we manually patched the factory here for test
    # We should actually use valid backend IDs or patch resolve_backend_definition
    monkeypatch.setattr(
        "voxkeep.modules.transcription.infrastructure.engine_factory.resolve_backend_definition",
        lambda bid: SimpleNamespace(backend_id=bid),
    )

    external = engine_factory.build_asr_engine(
        cfg=replace(app_config.asr, backend="funasr_ws_external"),
        stop_event=threading.Event(),
    )
    qwen = engine_factory.build_asr_engine(
        cfg=replace(app_config.asr, backend="qwen_vllm"),
        stop_event=threading.Event(),
    )

    assert external is sentinel_external
    assert qwen is sentinel_qwen


def test_build_transcription_module_supports_qwen_backend(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    new_asr = replace(app_config.asr, backend="qwen_vllm")
    monkeypatch.setattr(
        "voxkeep.modules.transcription.public.build_asr_engine",
        lambda cfg, stop_event: fake_engine,
    )

    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=threading.Event(),
        asr_cfg=new_asr,
        storage_cfg=app_config.storage,
    )

    assert module is not None


def test_transcription_engine_contract_exposes_join_method() -> None:
    assert "join" in TranscriptionEngine.__dict__


def test_funasr_ws_engine_emits_backend_transcript_events(app_config: AppConfig) -> None:
    stop_event = threading.Event()
    engine = FunAsrWsEngine(cfg=app_config.asr, stop_event=stop_event)

    class _FakeWebSocket:
        def __init__(self, messages: list[str]) -> None:
            self._messages = messages

        def __aiter__(self):
            async def _iterate():
                for message in self._messages:
                    yield message

            return _iterate()

    asyncio.run(
        engine._receiver(
            _FakeWebSocket(
                [
                    '{"type": "final", "text": "hello", "start": 1.0, "end": 1.2, "segment_id": "seg-1"}'
                ]
            )
        )
    )

    event = engine.final_queue.get_nowait()

    assert isinstance(event, BackendTranscriptEvent)
    assert event.event_type == "final"
    assert event.is_final is True
    assert event.text == "hello"


def test_backend_transcript_event_marks_final_events() -> None:
    event = BackendTranscriptEvent(
        segment_id="seg-1",
        text="hello",
        start_ts=1.0,
        end_ts=1.2,
        event_type="final",
    )

    assert event.is_final is True
