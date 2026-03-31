import queue
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
