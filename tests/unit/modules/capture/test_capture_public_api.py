from __future__ import annotations

import queue
import threading
import time

from voxkeep.shared.events import CaptureCommand
from voxkeep.modules.capture.public import build_capture_module
from voxkeep.shared.config import AppConfig
from voxkeep.shared.types import SpeechBoundaryDetected, TranscriptFinalized, WakeDetected


def test_capture_module_emits_capture_completed_and_forwards_command(
    app_config: AppConfig,
) -> None:
    downstream_q: queue.Queue[CaptureCommand] = queue.Queue()
    storage_q = queue.Queue()
    stop_event = threading.Event()
    seen: list[str] = []

    module = build_capture_module(
        downstream_queue=downstream_q,
        storage_queue=storage_q,
        stop_event=stop_event,
        cfg=app_config,
    )
    module.subscribe_capture_completed(lambda event: seen.append(event.text))
    module.start()

    module.accept_wake(WakeDetected(ts=1.0, score=0.9, keyword="alexa"))
    module.accept_transcript(
        TranscriptFinalized(
            segment_id="seg-1",
            text="hello world",
            start_ts=1.0,
            end_ts=1.3,
        )
    )
    module.accept_vad(SpeechBoundaryDetected(ts=1.1, event_type="speech_start", score=0.8))
    module.accept_vad(SpeechBoundaryDetected(ts=1.4, event_type="speech_end", score=0.1))

    deadline = time.time() + 2.0
    while time.time() < deadline and not seen:
        time.sleep(0.02)

    stop_event.set()
    module.join(timeout=2)

    command = downstream_q.get_nowait()
    assert command.action == "inject_text"
    assert seen == ["hello world"]


def test_capture_module_stop_sets_stop_event(app_config: AppConfig) -> None:
    stop_event = threading.Event()
    module = build_capture_module(
        downstream_queue=queue.Queue(),
        storage_queue=queue.Queue(),
        stop_event=stop_event,
        cfg=app_config,
    )

    module.stop()

    assert stop_event.is_set() is True
