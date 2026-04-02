from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.modules.transcription.infrastructure.qwen_vllm import QwenVllmEngine


class _FakeWebSocket:
    def __init__(self, messages: list[Any]) -> None:
        self._messages = messages

    def __aiter__(self):
        async def _iterate():
            for message in self._messages:
                yield message

        return _iterate()


def test_parse_stream_event_maps_final_transcript(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())
    payload = {
        "type": "transcript",
        "delta": {"text": "hello world"},
        "finish_reason": "stop",
        "start": 1.0,
        "end": 1.2,
        "segment_id": "seg-1",
    }

    event = engine._parse_stream_event(payload)

    assert event == BackendTranscriptEvent(
        segment_id="seg-1",
        text="hello world",
        start_ts=1.0,
        end_ts=1.2,
        event_type="final",
    )


def test_receiver_discards_partial_events(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())

    partial = {
        "type": "transcript",
        "delta": {"text": "hel"},
        "finish_reason": None,
        "start": 1.0,
        "end": 1.1,
        "segment_id": "seg-1",
    }

    assert engine._parse_stream_event(partial) is None
    asyncio.run(engine._receiver(_FakeWebSocket([json.dumps(partial)])))
    assert engine.final_queue.empty()
