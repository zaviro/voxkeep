import queue
import threading
import time

import numpy as np

from asr_ol.core.events import ProcessedFrame
from asr_ol.infra.vad.silero_worker import SileroVadWorker
from asr_ol.infra.wake.openwakeword_worker import OpenWakeWordWorker


class FakeWakeScorer:
    def score(self, frame: ProcessedFrame) -> float:
        _ = frame
        return 0.9


class FakeVadScorer:
    def __init__(self, scores: list[float]):
        self._scores = scores
        self._idx = 0

    def speech_score(self, frame: ProcessedFrame) -> float:
        _ = frame
        if self._idx >= len(self._scores):
            return 0.0
        score = self._scores[self._idx]
        self._idx += 1
        return score


def _frame(i: int, start: float, dur: float = 0.01) -> ProcessedFrame:
    return ProcessedFrame(
        frame_id=i,
        data_int16=(b"\x00\x00" * 160),
        pcm_f32=np.zeros(160, dtype=np.float32),
        sample_rate=16000,
        ts_start=start,
        ts_end=start + dur,
    )


def test_wake_worker_emits_event():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    out_q = queue.Queue()
    stop = threading.Event()

    worker = OpenWakeWordWorker(
        in_queue=in_q,
        out_queue=out_q,
        stop_event=stop,
        threshold=0.5,
        scorer=FakeWakeScorer(),
        keyword="wake",
    )

    worker.start()
    in_q.put(_frame(1, time.time()))
    time.sleep(0.05)
    stop.set()
    worker.join(timeout=1)

    event = out_q.get_nowait()
    assert event.keyword == "wake"


def test_vad_worker_emits_start_and_end():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    out_q = queue.Queue()
    stop = threading.Event()

    worker = SileroVadWorker(
        in_queue=in_q,
        out_queue=out_q,
        stop_event=stop,
        speech_threshold=0.5,
        silence_ms=20,
        scorer=FakeVadScorer([0.9, 0.9, 0.1, 0.1, 0.1]),
    )

    worker.start()
    base = time.time()
    for i in range(5):
        in_q.put(_frame(i + 1, base + i * 0.01))

    time.sleep(0.1)
    stop.set()
    worker.join(timeout=1)

    events = [out_q.get_nowait(), out_q.get_nowait()]
    assert events[0].event_type == "speech_start"
    assert events[1].event_type == "speech_end"
