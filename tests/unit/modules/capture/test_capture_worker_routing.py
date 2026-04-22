from __future__ import annotations

import queue
import threading

from voxkeep.modules.capture.domain.capture_fsm import CaptureWindow
from voxkeep.modules.capture.infrastructure.capture_worker import CaptureWorker
from voxkeep.shared.events import AsrFinalEvent, VadEvent, WakeEvent


class FakeFSM:
    def on_wake(self, event: WakeEvent) -> None:
        _ = event

    def on_vad(self, event: VadEvent) -> CaptureWindow | None:
        if event.event_type == "speech_end":
            return CaptureWindow(
                session_id=1,
                keyword="hey_jarvis",
                start_ts=1.0,
                end_ts=1.5,
            )
        return None

    def tick(self) -> None:
        return


class FakeExtractor:
    def on_asr_final(self, event: AsrFinalEvent) -> None:
        _ = event

    def extract(self, start_ts: float, end_ts: float) -> str:
        _ = (start_ts, end_ts)
        return "route me"


def test_capture_worker_routes_action_by_keyword():
    wake_q: queue.Queue[WakeEvent] = queue.Queue()
    vad_q: queue.Queue[VadEvent] = queue.Queue()
    asr_q: queue.Queue[AsrFinalEvent] = queue.Queue()
    out_q = queue.Queue()
    storage_q = queue.Queue()

    worker = CaptureWorker(
        wake_queue=wake_q,
        vad_queue=vad_q,
        asr_queue=asr_q,
        out_queue=out_q,
        storage_queue=storage_q,
        stop_event=threading.Event(),
        fsm=FakeFSM(),
        transcript_extractor=FakeExtractor(),
        action_by_keyword={"hey_jarvis": "openclaw_agent", "alexa": "inject_text"},
        default_action="inject_text",
    )

    wake_q.put(WakeEvent(ts=1.0, score=0.8, keyword="hey_jarvis"))
    asr_q.put(AsrFinalEvent(segment_id="a", text="ignored", start_ts=1.1, end_ts=1.2))
    vad_q.put(VadEvent(ts=1.5, event_type="speech_end", score=0.1))

    worker._consume_once()

    cmd = out_q.get_nowait()
    assert cmd.keyword == "hey_jarvis"
    assert cmd.action == "openclaw_agent"
    assert cmd.text == "route me"
