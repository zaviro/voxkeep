from __future__ import annotations

import json
import queue
import subprocess
import threading

from voxkeep.modules.capture.application.transcript_extractor import InMemoryTranscriptExtractor
from voxkeep.modules.capture.domain.capture_fsm import CaptureFSM
from voxkeep.modules.capture.infrastructure.capture_worker import CaptureWorker
from voxkeep.shared.events import AsrFinalEvent, VadEvent, WakeEvent


def test_openclaw_triggered_by_wake_with_asr_hi_returns_payload(require_openclaw_real: None):
    prompt_text = "请忽略其他内容，只回复：你好这里是openclaw"
    agents = subprocess.run(
        ["openclaw", "agents", "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(agents.stdout)
    assert any(item.get("id") == "main" for item in payload if isinstance(item, dict))

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
        fsm=CaptureFSM(pre_roll_ms=200, armed_timeout_ms=2000),
        transcript_extractor=InMemoryTranscriptExtractor(),
        action_by_keyword={"hey_jarvis": "openclaw_agent"},
        default_action="inject_text",
    )

    wake_q.put(WakeEvent(ts=10.0, score=0.9, keyword="hey_jarvis"))
    asr_q.put(
        AsrFinalEvent(
            segment_id="seg-1",
            text=prompt_text,
            start_ts=10.05,
            end_ts=10.3,
        )
    )
    vad_q.put(VadEvent(ts=10.1, event_type="speech_start", score=0.9))
    vad_q.put(VadEvent(ts=10.5, event_type="speech_end", score=0.1))
    worker._consume_once()
    worker._consume_once()

    cmd = out_q.get_nowait()
    assert cmd.action == "openclaw_agent"
    assert cmd.keyword == "hey_jarvis"
    assert cmd.text == prompt_text

    proc = subprocess.run(
        [
            "openclaw",
            "agent",
            "--agent",
            "main",
            "--message",
            cmd.text,
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    texts = [
        item.get("text", "")
        for item in result.get("result", {}).get("payloads", [])
        if isinstance(item, dict)
    ]
    assert any("你好这里是openclaw" in text for text in texts)
