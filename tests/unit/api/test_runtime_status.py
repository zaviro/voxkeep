import queue
import threading

from voxkeep.api.runtime_status import collect_runtime_status, collect_runtime_status_dict


class FakeRuntime:
    def __init__(self):
        self.stop_event = threading.Event()
        self.raw_queue = queue.Queue()
        self.wake_audio_queue = queue.Queue()
        self.vad_audio_queue = queue.Queue()
        self.asr_audio_queue = queue.Queue()
        self.wake_event_queue = queue.Queue()
        self.vad_event_queue = queue.Queue()
        self.asr_event_bus = queue.Queue()
        self.capture_cmd_queue = queue.Queue()
        self.storage_queue = queue.Queue()


def test_collect_runtime_status_has_expected_shape():
    runtime = FakeRuntime()
    runtime.raw_queue.put(1)

    status = collect_runtime_status(runtime)

    assert status.running is True
    assert status.queue_sizes["raw_queue"] == 1
    assert "T" in status.created_at


def test_collect_runtime_status_dict_works_after_stop():
    runtime = FakeRuntime()
    runtime.stop_event.set()

    payload = collect_runtime_status_dict(runtime)

    assert payload["running"] is False
    assert payload["queue_sizes"]["storage_queue"] == 0
