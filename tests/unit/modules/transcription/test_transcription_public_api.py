from __future__ import annotations

import queue
import threading
import time

import numpy as np

from asr_ol.shared.events import AsrFinalEvent
from asr_ol.modules.transcription.public import build_transcription_module
from asr_ol.shared.config import AppConfig
from asr_ol.shared.types import AudioFrame


class _FakeEngine:
    def __init__(self) -> None:
        self.final_queue: queue.Queue[AsrFinalEvent] = queue.Queue()
        self.started = 0
        self.closed = 0
        self.submitted = []

    def start(self) -> None:
        self.started += 1

    def submit_frame(self, frame) -> None:  # type: ignore[no-untyped-def]
        self.submitted.append(frame)

    def close(self) -> None:
        self.closed += 1

    def join(self, timeout: float | None = None) -> None:
        _ = timeout


def test_transcription_module_submits_audio_and_emits_public_events(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "asr_ol.modules.transcription.public.FunAsrWsEngine",
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
        cfg=app_config,
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
        AsrFinalEvent(
            segment_id="seg-1",
            text="hello",
            start_ts=1.0,
            end_ts=1.2,
        )
    )

    deadline = time.time() + 2.0
    while time.time() < deadline and not seen:
        time.sleep(0.02)

    stop_event.set()
    module.join(timeout=2)

    assert len(fake_engine.submitted) == 1
    assert seen == ["hello"]


def test_transcription_module_submit_audio_drops_when_queue_is_full(
    monkeypatch, app_config: AppConfig
) -> None:
    fake_engine = _FakeEngine()
    monkeypatch.setattr(
        "asr_ol.modules.transcription.public.FunAsrWsEngine",
        lambda cfg, stop_event: fake_engine,
    )
    stop_event = threading.Event()
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=stop_event,
        cfg=app_config,
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
        "asr_ol.modules.transcription.public.FunAsrWsEngine",
        lambda cfg, stop_event: fake_engine,
    )
    stop_event = threading.Event()
    module = build_transcription_module(
        capture_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=stop_event,
        cfg=app_config,
    )

    module.stop()

    assert stop_event.is_set() is True
