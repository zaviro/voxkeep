import queue
import threading
import time

from voxkeep.modules.runtime.infrastructure.audio_bus import AudioBus
from voxkeep.shared.events import RawAudioChunk


def test_fanout_and_preprocess_once():
    stop_event = __import__("threading").Event()
    q_in = queue.Queue()
    q_w = queue.Queue()
    q_v = queue.Queue()
    q_a = queue.Queue()

    bus = AudioBus(q_in, q_w, q_v, q_a, stop_event)

    chunk = RawAudioChunk(
        data=(b"\x00\x00" * 320),
        frames=320,
        sample_rate=16000,
        channels=1,
        ts=time.time(),
    )
    q_in.put(chunk)
    bus.run_once(timeout=0.01)

    fw = q_w.get_nowait()
    fv = q_v.get_nowait()
    fa = q_a.get_nowait()
    assert fw.frame_id == fv.frame_id == fa.frame_id


def test_audio_bus_run_once_returns_on_empty_queue():
    stop_event = threading.Event()
    bus = AudioBus(queue.Queue(), queue.Queue(), queue.Queue(), queue.Queue(), stop_event)

    bus.run_once(timeout=0.0)

    assert bus.dropped == {"wake": 0, "vad": 0, "asr": 0}


def test_audio_bus_tracks_drop_counts_per_target_queue():
    stop_event = threading.Event()
    q_in: queue.Queue[RawAudioChunk] = queue.Queue()
    q_w: queue.Queue = queue.Queue(maxsize=1)
    q_v: queue.Queue = queue.Queue(maxsize=1)
    q_a: queue.Queue = queue.Queue(maxsize=1)
    bus = AudioBus(q_in, q_w, q_v, q_a, stop_event)

    q_w.put(object())
    q_a.put(object())
    q_in.put(
        RawAudioChunk(
            data=(b"\x00\x00" * 320),
            frames=320,
            sample_rate=16000,
            channels=1,
            ts=time.time(),
        )
    )

    bus.run_once(timeout=0.01)

    assert bus.dropped == {"wake": 1, "vad": 0, "asr": 1}


def test_audio_bus_start_is_idempotent(monkeypatch):
    starts: list[tuple[object, object, object]] = []

    class FakeThread:
        def __init__(self, target, name, daemon):  # type: ignore[no-untyped-def]
            starts.append((target, name, daemon))

        def start(self) -> None:
            return

        def join(self, timeout: float | None = None) -> None:
            _ = timeout

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(threading, "Thread", FakeThread)
    bus = AudioBus(queue.Queue(), queue.Queue(), queue.Queue(), queue.Queue(), threading.Event())

    bus.start()
    bus.start()

    assert len(starts) == 1


def test_audio_bus_run_processes_remaining_items_after_stop():
    stop_event = threading.Event()
    q_in: queue.Queue[RawAudioChunk] = queue.Queue()
    q_w = queue.Queue()
    q_v = queue.Queue()
    q_a = queue.Queue()
    bus = AudioBus(q_in, q_w, q_v, q_a, stop_event)

    q_in.put(
        RawAudioChunk(
            data=(b"\x00\x00" * 320),
            frames=320,
            sample_rate=16000,
            channels=1,
            ts=time.time(),
        )
    )
    stop_event.set()

    bus._run()

    assert q_w.qsize() == 1
    assert q_v.qsize() == 1
    assert q_a.qsize() == 1
