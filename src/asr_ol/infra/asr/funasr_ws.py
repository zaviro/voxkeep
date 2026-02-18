from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from typing import Any
import uuid

from asr_ol.core.asr_engine import ASREngine
from asr_ol.core.config import AppConfig
from asr_ol.core.events import AsrFinalEvent, ProcessedFrame

logger = logging.getLogger(__name__)


class FunAsrWsEngine(ASREngine):
    def __init__(self, cfg: AppConfig, stop_event: threading.Event):
        self._cfg = cfg
        self._stop_event = stop_event
        self._in_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self._final_queue: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self._thread: threading.Thread | None = None

    @property
    def final_queue(self) -> queue.Queue[AsrFinalEvent]:
        return self._final_queue

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_thread, name="asr_engine", daemon=True)
        self._thread.start()

    def submit_frame(self, frame: ProcessedFrame) -> None:
        try:
            self._in_queue.put_nowait(frame)
        except queue.Full:
            logger.warning("asr input queue full; dropping frame_id=%s", frame.frame_id)

    def close(self) -> None:
        # Engine lifecycle follows stop_event; method kept for interface symmetry.
        logger.info("asr engine close requested")

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run_thread(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        backoff = self._cfg.asr_reconnect_initial_s
        max_backoff = self._cfg.asr_reconnect_max_s

        while not self._stop_event.is_set():
            try:
                await self._run_session()
                backoff = self._cfg.asr_reconnect_initial_s
            except Exception as exc:
                logger.warning("asr websocket session error=%s reconnect_in=%.1fs", exc, backoff)
                should_stop = await asyncio.to_thread(self._stop_event.wait, backoff)
                if should_stop:
                    break
                backoff = min(max_backoff, backoff * 2)

        logger.info("asr engine stopped")

    async def _run_session(self) -> None:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("websockets package is required") from exc

        url = self._cfg.asr_ws_url
        logger.info("asr websocket connecting url=%s", url)
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**22) as ws:
            logger.info("asr websocket connected")
            sender = asyncio.create_task(self._sender(ws))
            receiver = asyncio.create_task(self._receiver(ws))
            stopper = asyncio.create_task(asyncio.to_thread(self._stop_event.wait))

            done, pending = await asyncio.wait(
                {sender, receiver, stopper},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
            for task in done:
                if task.exception():
                    raise task.exception()

    async def _sender(self, ws: Any) -> None:
        while not self._stop_event.is_set() or not self._in_queue.empty():
            frame = await asyncio.to_thread(self._get_frame, 0.1)
            if frame is None:
                continue
            await ws.send(frame.data_int16)

    async def _receiver(self, ws: Any) -> None:
        async for raw in ws:
            if self._stop_event.is_set():
                return

            payload = self._parse_message(raw)
            if not payload:
                continue
            if not self._is_final(payload):
                continue

            text = str(payload.get("text") or payload.get("result") or "").strip()
            if not text:
                continue

            now = time.time()
            start_ts = float(payload.get("start") or payload.get("start_time") or now)
            end_ts = float(payload.get("end") or payload.get("end_time") or now)
            segment_id = str(payload.get("segment_id") or payload.get("sid") or uuid.uuid4())

            event = AsrFinalEvent(
                segment_id=segment_id,
                text=text,
                start_ts=start_ts,
                end_ts=end_ts,
                is_final=True,
            )
            try:
                self._final_queue.put_nowait(event)
            except queue.Full:
                logger.warning("asr final queue full; dropping segment_id=%s", segment_id)

    def _get_frame(self, timeout: float) -> ProcessedFrame | None:
        try:
            return self._in_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @staticmethod
    def _parse_message(raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, bytes):
            return None
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    @staticmethod
    def _is_final(payload: dict[str, Any]) -> bool:
        if payload.get("is_final") is True:
            return True
        if payload.get("sentence_end") is True:
            return True
        if payload.get("mode") == "final":
            return True
        if payload.get("type") == "final":
            return True
        return False
