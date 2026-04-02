from __future__ import annotations

import queue
import threading
from typing import get_args, get_origin, get_type_hints

import numpy as np
import pytest

from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.modules.transcription.contracts import TranscriptionBackendEvent
from voxkeep.shared.config import AppConfig
from voxkeep.shared.events import AsrFinalEvent, ProcessedFrame
from voxkeep.modules.transcription.infrastructure.asr_worker import AsrWorker


class FakeEngine:
    def __init__(self) -> None:
        self.started = 0
        self.closed = 0
        self.submitted: list[ProcessedFrame] = []
        self.join_timeouts: list[float | None] = []

    def start(self) -> None:
        self.started += 1

    def submit_frame(self, frame: ProcessedFrame) -> None:
        self.submitted.append(frame)

    def close(self) -> None:
        self.closed += 1

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)


def _frame(frame_id: int = 1, ts_start: float = 1.0) -> ProcessedFrame:
    return ProcessedFrame(
        frame_id=frame_id,
        data_int16=(b"\x00\x00" * 160),
        pcm_f32=np.zeros(160, dtype=np.float32),
        sample_rate=16000,
        ts_start=ts_start,
        ts_end=ts_start + 0.01,
    )


def _event(*, text: str = "hello", is_final: bool = True) -> AsrFinalEvent:
    return AsrFinalEvent(
        segment_id="seg-1",
        text=text,
        start_ts=1.0,
        end_ts=1.2,
        is_final=is_final,
    )


def _backend_event(*, text: str = "hello", event_type: str = "final") -> BackendTranscriptEvent:
    return BackendTranscriptEvent(
        segment_id="seg-1",
        text=text,
        start_ts=1.0,
        end_ts=1.2,
        event_type=event_type,
    )


@pytest.mark.parametrize(
    ("store_final_only", "expected_storage"),
    [
        (True, 1),
        (False, 1),
    ],
)
def test_drain_final_events_fanout_and_storage_policy(
    store_final_only: bool,
    expected_storage: int,
) -> None:
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=store_final_only,
    )

    event = _backend_event(text="hello", event_type="final")
    final_q.put(event)

    worker._drain_final_events()

    out_event = out_q.get_nowait()
    capture_event = capture_q.get_nowait()
    assert isinstance(out_event, AsrFinalEvent)
    assert isinstance(capture_event, AsrFinalEvent)
    assert out_event.text == event.text
    assert capture_event.text == event.text
    assert storage_q.qsize() == expected_storage


def test_drain_final_events_ignores_backend_partial_events() -> None:
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=True,
    )

    final_q.put(_backend_event(event_type="partial"))

    worker._drain_final_events()

    assert out_q.empty()
    assert capture_q.empty()
    assert storage_q.empty()


def test_drain_final_events_ignores_backend_partial_events_when_store_final_only_is_false() -> None:
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=False,
    )

    final_q.put(_backend_event(event_type="partial"))

    worker._drain_final_events()

    assert out_q.empty()
    assert capture_q.empty()
    assert storage_q.empty()


def test_drain_final_events_normalizes_backend_final_events() -> None:
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=True,
    )

    final_q.put(_backend_event(text="normalized"))

    worker._drain_final_events()

    out_event = out_q.get_nowait()
    capture_event = capture_q.get_nowait()
    storage_event = storage_q.get_nowait()

    assert isinstance(out_event, AsrFinalEvent)
    assert out_event.text == "normalized"
    assert capture_event.text == "normalized"
    assert storage_event.text == "normalized"


def test_asr_worker_final_input_queue_is_backend_neutral() -> None:
    hints = get_type_hints(AsrWorker.__init__)
    final_in_queue_type = hints["final_in_queue"]

    assert get_origin(final_in_queue_type) is queue.Queue
    assert get_args(final_in_queue_type) == (TranscriptionBackendEvent,)


def test_to_asr_final_event_accepts_structural_backend_event() -> None:
    from voxkeep.modules.transcription.application.transcription_service import to_asr_final_event
    from types import SimpleNamespace

    event = SimpleNamespace(
        segment_id="seg-1",
        text="structural",
        start_ts=1.0,
        end_ts=1.2,
        is_final=True,
    )

    normalized = to_asr_final_event(event)

    assert isinstance(normalized, AsrFinalEvent)
    assert normalized.text == "structural"


def test_run_submits_audio_and_closes_engine():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=True,
    )

    in_q.put(_frame())
    final_q.put(_backend_event())
    stop.set()

    worker._run()

    assert len(engine.submitted) == 1
    assert out_q.qsize() == 1
    assert capture_q.qsize() == 1
    assert storage_q.qsize() == 1
    assert engine.closed == 1


def test_join_forwards_timeout_to_engine():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=True,
    )

    worker.join(timeout=1.5)

    assert engine.join_timeouts == [1.5]


def test_start_is_idempotent_for_engine(app_config: AppConfig):
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    final_q: queue.Queue[BackendTranscriptEvent] = queue.Queue()
    out_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    capture_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    storage_q = queue.Queue()
    stop = threading.Event()
    engine = FakeEngine()

    worker = AsrWorker(
        in_queue=in_q,
        final_in_queue=final_q,
        out_queue=out_q,
        capture_queue=capture_q,
        storage_queue=storage_q,
        stop_event=stop,
        engine=engine,
        store_final_only=True,
    )

    worker.start()
    worker.start()
    stop.set()
    worker.join(timeout=1)

    assert engine.started == 1
