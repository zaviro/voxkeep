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


def test_clean_realtime_text_removes_language_prefix_and_tags(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())

    cleaned = engine._clean_realtime_text(
        "language English<asr_text> Hello world\nlanguage Chinese<asr_text> again"
    )

    assert cleaned == "Hello world again"


def test_clean_realtime_text_merges_repeated_segments(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())

    cleaned = engine._clean_realtime_text(
        "\n".join(
            [
                "language English<asr_text>Oh yeah, yeah. He wasn't even that big when I started listening.",
                "language English<asr_text>Hmm. Oh yeah, yeah. He wasn't even that big when I started listening.",
                "language English<asr_text>To him, but and his solo music didn't do overly.",
                "language English<asr_text>Well, but he did very well when he started writing for other people.",
            ]
        )
    )

    assert "language" not in cleaned
    assert "<asr_text>" not in cleaned
    assert cleaned.count("He wasn't even that big when I started listening.") == 1
    assert cleaned.endswith("he started writing for other people.")


def test_parse_stream_event_maps_realtime_done_to_final_transcript(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())
    payload = {
        "type": "transcription.done",
        "text": (
            "language English<asr_text>Oh yeah, yeah. He wasn't even that big when I started listening.\n"
            "language English<asr_text>To him, but and his solo music didn't do overly well."
        ),
        "usage": {"total_tokens": 42},
    }

    event = engine._parse_stream_event(payload)

    assert event == BackendTranscriptEvent(
        segment_id=event.segment_id,
        text=(
            "Oh yeah, yeah. He wasn't even that big when I started listening. "
            "To him, but and his solo music didn't do overly well."
        ),
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        event_type="final",
    )


def test_parse_stream_event_discards_realtime_delta_payloads(app_config) -> None:
    engine = QwenVllmEngine(cfg=app_config, stop_event=threading.Event())

    assert engine._parse_stream_event({"type": "transcription.delta", "delta": "hello"}) is None
