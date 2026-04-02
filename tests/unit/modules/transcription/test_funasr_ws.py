from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import threading
from typing import Any

import numpy as np
import pytest

from voxkeep.shared.config import AppConfig
from voxkeep.shared.events import ProcessedFrame
from voxkeep.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine


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


class FakeTask:
    def __init__(self, *, exception: Exception | None = None) -> None:
        self._exception = exception
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def exception(self) -> Exception | None:
        return self._exception


class FakeConnectContext:
    def __init__(self, ws: object) -> None:
        self._ws = ws

    async def __aenter__(self) -> object:
        return self._ws

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


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


def test_run_session_builds_connect_url_from_new_asr_fields(
    app_config: AppConfig, monkeypatch
) -> None:
    cfg = replace(
        app_config,
        asr_external_host="10.0.0.8",
        asr_external_port=3210,
        asr_external_path="/ws",
        asr_external_use_ssl=True,
    )
    engine = FunAsrWsEngine(cfg=cfg, stop_event=threading.Event())
    connect_urls: list[str] = []
    created: list[FakeTask] = []

    monkeypatch.setattr(
        "websockets.connect",
        lambda url, **kwargs: connect_urls.append(url) or FakeConnectContext(FakeWsSender()),
    )

    async def fake_sender(ws: object) -> None:
        _ = ws

    async def fake_receiver(ws: object) -> None:
        _ = ws

    async def fake_to_thread(func, *args):  # type: ignore[no-untyped-def]
        _ = (func, args)
        return True

    def fake_create_task(coro):  # type: ignore[no-untyped-def]
        coro.close()
        task = FakeTask()
        created.append(task)
        return task

    async def fake_wait(tasks, return_when):  # type: ignore[no-untyped-def]
        _ = return_when
        return {created[2]}, {created[0], created[1]}

    monkeypatch.setattr(engine, "_sender", fake_sender)
    monkeypatch.setattr(engine, "_receiver", fake_receiver)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(asyncio, "wait", fake_wait)

    asyncio.run(engine._run_session())

    assert connect_urls == [cfg.asr_ws_url]


def test_submit_frame_drops_when_input_queue_is_full(app_config: AppConfig) -> None:
    stop = threading.Event()
    engine = FunAsrWsEngine(cfg=replace(app_config, max_queue_size=1), stop_event=stop)

    engine.submit_frame(_frame(frame_id=1))
    engine.submit_frame(_frame(frame_id=2))

    queued = engine._get_frame(timeout=0.0)
    assert queued is not None
    assert queued.frame_id == 1
    assert engine._get_frame(timeout=0.0) is None


def test_receiver_returns_immediately_when_stop_event_is_set(app_config: AppConfig) -> None:
    stop = threading.Event()
    stop.set()
    engine = FunAsrWsEngine(cfg=app_config, stop_event=stop)
    ws = FakeWsReceiver(
        messages=[
            '{"mode": "final", "text": "hello", "start": 1.0, "end": 1.1, "segment_id": "s1"}',
        ]
    )

    asyncio.run(engine._receiver(ws))

    assert engine.final_queue.empty()


def test_get_frame_returns_none_on_empty_queue(app_config: AppConfig) -> None:
    engine = FunAsrWsEngine(cfg=app_config, stop_event=threading.Event())

    assert engine._get_frame(timeout=0.0) is None


def test_build_ws_config_uses_sample_rate_from_config(app_config: AppConfig) -> None:
    cfg = replace(app_config, sample_rate=22050)
    engine = FunAsrWsEngine(cfg=cfg, stop_event=threading.Event())

    payload = engine._build_ws_config(is_speaking=True)

    assert payload["audio_fs"] == 22050
    assert payload["is_speaking"] is True


def test_run_session_cancels_pending_tasks_when_stopper_finishes(
    app_config: AppConfig, monkeypatch
) -> None:
    engine = FunAsrWsEngine(cfg=app_config, stop_event=threading.Event())
    created: list[FakeTask] = []
    wait_tasks: list[FakeTask] = []

    monkeypatch.setattr(
        "websockets.connect",
        lambda *args, **kwargs: FakeConnectContext(object()),
    )

    async def fake_sender(ws: object) -> None:
        _ = ws

    async def fake_receiver(ws: object) -> None:
        _ = ws

    async def fake_to_thread(func, *args):  # type: ignore[no-untyped-def]
        _ = (func, args)
        return True

    def fake_create_task(coro):  # type: ignore[no-untyped-def]
        coro.close()
        task = FakeTask()
        created.append(task)
        return task

    async def fake_wait(tasks, return_when):  # type: ignore[no-untyped-def]
        _ = return_when
        wait_tasks.extend(tasks)
        return {created[2]}, {created[0], created[1]}

    monkeypatch.setattr(engine, "_sender", fake_sender)
    monkeypatch.setattr(engine, "_receiver", fake_receiver)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(asyncio, "wait", fake_wait)

    asyncio.run(engine._run_session())

    assert len(created) == 3
    assert set(wait_tasks) == set(created)
    assert created[0].cancelled is True
    assert created[1].cancelled is True
    assert created[2].cancelled is False


def test_run_session_propagates_sender_exception(app_config: AppConfig, monkeypatch) -> None:
    engine = FunAsrWsEngine(cfg=app_config, stop_event=threading.Event())
    sender_exc = RuntimeError("sender boom")
    created: list[FakeTask] = []

    monkeypatch.setattr(
        "websockets.connect",
        lambda *args, **kwargs: FakeConnectContext(object()),
    )

    def fake_create_task(coro):  # type: ignore[no-untyped-def]
        coro.close()
        task = FakeTask(exception=sender_exc if not created else None)
        created.append(task)
        return task

    async def fake_wait(tasks, return_when):  # type: ignore[no-untyped-def]
        _ = (tasks, return_when)
        return {created[0]}, {created[1], created[2]}

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(asyncio, "wait", fake_wait)

    with pytest.raises(RuntimeError, match="sender boom"):
        asyncio.run(engine._run_session())
