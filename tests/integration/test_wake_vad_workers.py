import queue
import threading
import time

import numpy as np

from voxkeep.shared.events import ProcessedFrame
from voxkeep.modules.capture.infrastructure.silero_worker import SileroVadWorker
from voxkeep.modules.capture.infrastructure.openwakeword_worker import OpenWakeWordWorker


class FakeWakeScorer:
    def score(self, frame: ProcessedFrame) -> dict[str, float]:
        _ = frame
        return {"alexa": 0.1, "hey_jarvis": 0.9}


class HighScoreWakeScorer:
    def score(self, frame: ProcessedFrame) -> dict[str, float]:
        _ = frame
        return {"alexa": 0.8, "hey_jarvis": 0.9}


class NoMatchWakeScorer:
    def score(self, frame: ProcessedFrame) -> dict[str, float]:
        _ = frame
        return {"alexa": 0.2, "hey_jarvis": 0.3}


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
        rules=[
            {"keyword": "alexa", "threshold": 0.5, "enabled": True, "action": "inject_text"},
            {
                "keyword": "hey_jarvis",
                "threshold": 0.5,
                "enabled": True,
                "action": "openclaw_agent",
            },
        ],
        scorer=FakeWakeScorer(),
    )

    worker.start()
    in_q.put(_frame(1, time.time()))
    time.sleep(0.05)
    stop.set()
    worker.join(timeout=1)

    event = out_q.get_nowait()
    assert event.keyword == "hey_jarvis"


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


def test_wake_worker_no_match_emits_nothing():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    out_q = queue.Queue()
    stop = threading.Event()
    worker = OpenWakeWordWorker(
        in_queue=in_q,
        out_queue=out_q,
        stop_event=stop,
        rules=[
            {"keyword": "alexa", "threshold": 0.5, "enabled": True, "action": "inject_text"},
            {
                "keyword": "hey_jarvis",
                "threshold": 0.6,
                "enabled": True,
                "action": "openclaw_agent",
            },
        ],
        scorer=NoMatchWakeScorer(),
    )

    worker.start()
    in_q.put(_frame(1, time.time()))
    time.sleep(0.05)
    stop.set()
    worker.join(timeout=1)

    assert out_q.empty()


def test_wake_worker_chooses_highest_score_above_threshold():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    out_q: queue.Queue = queue.Queue()
    stop = threading.Event()
    worker = OpenWakeWordWorker(
        in_queue=in_q,
        out_queue=out_q,
        stop_event=stop,
        rules=[
            {"keyword": "alexa", "threshold": 0.5, "enabled": True, "action": "inject_text"},
            {
                "keyword": "hey_jarvis",
                "threshold": 0.5,
                "enabled": True,
                "action": "openclaw_agent",
            },
        ],
        scorer=HighScoreWakeScorer(),
    )

    assert worker._detect(_frame(1, 1.0)) is not None
    assert worker._detect(_frame(2, 2.0)).keyword == "hey_jarvis"


def test_wake_worker_drops_event_when_output_queue_is_full():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    out_q: queue.Queue = queue.Queue(maxsize=1)
    stop = threading.Event()
    worker = OpenWakeWordWorker(
        in_queue=in_q,
        out_queue=out_q,
        stop_event=stop,
        rules=[
            {"keyword": "alexa", "threshold": 0.5, "enabled": True, "action": "inject_text"},
            {
                "keyword": "hey_jarvis",
                "threshold": 0.5,
                "enabled": True,
                "action": "openclaw_agent",
            },
        ],
        scorer=FakeWakeScorer(),
    )

    out_q.put(object())

    assert worker._detect(_frame(1, 1.0)) is not None
    worker._run = lambda: None  # type: ignore[method-assign]
    assert out_q.qsize() == 1


def test_vad_worker_resets_silence_counter_when_speech_resumes():
    in_q: queue.Queue[ProcessedFrame] = queue.Queue()
    out_q = queue.Queue()
    stop = threading.Event()
    worker = SileroVadWorker(
        in_queue=in_q,
        out_queue=out_q,
        stop_event=stop,
        speech_threshold=0.5,
        silence_ms=20,
        scorer=FakeVadScorer([0.9, 0.1, 0.9, 0.1, 0.1, 0.1]),
    )

    worker.start()
    base = time.time()
    for i in range(6):
        in_q.put(_frame(i + 1, base + i * 0.01))

    time.sleep(0.1)
    stop.set()
    worker.join(timeout=1)

    events = [out_q.get_nowait(), out_q.get_nowait()]
    assert events[0].event_type == "speech_start"
    assert events[1].event_type == "speech_end"


def test_vad_worker_drops_event_when_output_queue_is_full():
    out_q: queue.Queue = queue.Queue(maxsize=1)
    stop = threading.Event()
    worker = SileroVadWorker(
        in_queue=queue.Queue(),
        out_queue=out_q,
        stop_event=stop,
        speech_threshold=0.5,
        silence_ms=20,
        scorer=FakeVadScorer([0.9]),
    )
    out_q.put(object())

    worker._emit(
        __import__("voxkeep.shared.events", fromlist=["VadEvent"]).VadEvent(
            ts=1.0, event_type="speech_start", score=0.9
        )
    )

    assert out_q.qsize() == 1
