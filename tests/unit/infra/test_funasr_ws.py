from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import threading
from typing import Any

import numpy as np
import pytest

from asr_ol.shared.config import AppConfig
from asr_ol.shared.events import ProcessedFrame
from asr_ol.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine


class FakeWsReceiver:
    def __init__(self, messages: list[Any]) -> None:
        self._messages = messages
        self._idx = 0

    def __aiter__(self) -> "FakeWsReceiver":
        return self

    async def __anext__(self) -> Any:
        if self._idx >= len(self._messages):
            raise StopAsyncIteration
        item = self._messages[self._idx]
        self._idx += 1
        return item


class FakeWsSender:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    async def send(self, payload: Any) -> None:
        self.sent.append(payload)


def _frame(frame_id: int = 1, ts_start: float = 1.0) -> ProcessedFrame:
    return ProcessedFrame(
        frame_id=frame_id,
        data_int16=(b"\x00\x00" * 160),
        pcm_f32=np.zeros(160, dtype=np.float32),
        sample_rate=16000,
        ts_start=ts_start,
        ts_end=ts_start + 0.01,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"bytes", None),
        ("not-json", None),
        ("[]", None),
        ('{"text": "ok"}', {"text": "ok"}),
    ],
)
def test_parse_message(raw: Any, expected: dict[str, Any] | None):
    assert FunAsrWsEngine._parse_message(raw) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"is_final": True}, True),
        ({"sentence_end": True}, True),
        ({"mode": "final"}, True),
        ({"type": "final"}, True),
        ({"mode": "online"}, False),
    ],
)
def test_is_final(payload: dict[str, Any], expected: bool):
    assert FunAsrWsEngine._is_final(payload) is expected


def test_receiver_only_emits_final_text_events(app_config: AppConfig):
    stop = threading.Event()
    engine = FunAsrWsEngine(cfg=app_config, stop_event=stop)
    ws = FakeWsReceiver(
        messages=[
            b"ignore-bytes",
            '{"mode": "online", "text": "partial"}',
            '{"mode": "final", "text": "  hello  ", "start": 1.0, "end": 1.3, "segment_id": "s1"}',
            '{"sentence_end": true, "result": "world", "start_time": 2.0, "end_time": 2.2, "sid": "s2"}',
            '{"is_final": true, "text": "   "}',
        ]
    )

    asyncio.run(engine._receiver(ws))

    first = engine.final_queue.get_nowait()
    second = engine.final_queue.get_nowait()

    assert first.segment_id == "s1"
    assert first.text == "hello"
    assert second.segment_id == "s2"
    assert second.text == "world"


def test_sender_wraps_audio_with_start_and_end_config(app_config: AppConfig):
    stop = threading.Event()
    engine = FunAsrWsEngine(cfg=app_config, stop_event=stop)
    ws = FakeWsSender()

    engine.submit_frame(_frame())
    stop.set()

    asyncio.run(engine._sender(ws))

    assert len(ws.sent) == 3
    start_payload = json.loads(ws.sent[0])
    end_payload = json.loads(ws.sent[-1])

    assert start_payload["is_speaking"] is True
    assert isinstance(ws.sent[1], bytes)
    assert end_payload["is_speaking"] is False


def test_run_reconnects_after_failure(app_config: AppConfig, monkeypatch):
    cfg = replace(app_config, asr_reconnect_initial_s=0.001, asr_reconnect_max_s=0.004)
    stop = threading.Event()
    engine = FunAsrWsEngine(cfg=cfg, stop_event=stop)

    attempts: list[int] = []

    async def _fake_run_session() -> None:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("boom")
        stop.set()

    monkeypatch.setattr(engine, "_run_session", _fake_run_session)

    asyncio.run(engine._run())

    assert len(attempts) == 2
