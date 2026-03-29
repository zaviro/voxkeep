"""FunASR websocket engine adapter implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from typing import Any
import uuid

from asr_ol.shared.interfaces import ASREngine
from asr_ol.shared.config import AppConfig
from asr_ol.shared.events import AsrFinalEvent, ProcessedFrame
from asr_ol.shared.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)


_FRAME_POLL_TIMEOUT_S = 0.1


class FunAsrWsEngine(ASREngine):
    """ASR engine implementation backed by FunASR websocket sessions."""

    def __init__(self, cfg: AppConfig, stop_event: threading.Event):
        """Initialize websocket engine queues and lifecycle state."""
        self._cfg = cfg
        self._stop_event = stop_event
        self._in_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self._final_queue: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self._thread: threading.Thread | None = None

    @property
    def final_queue(self) -> queue.Queue[AsrFinalEvent]:
        """Return queue receiving finalized transcript events."""
        return self._final_queue

    def start(self) -> None:
        """Start background asyncio loop thread once."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run_thread, name="asr_engine", daemon=True)
        self._thread.start()

    def submit_frame(self, frame: ProcessedFrame) -> None:
        """Submit one preprocessed audio frame for upstream websocket sender."""
        put_nowait_or_drop(
            self._in_queue,
            frame,
            logger=logger,
            warning=f"asr input queue full; dropping frame_id={frame.frame_id}",
        )

    def close(self) -> None:
        """Request engine close; actual lifecycle follows stop event."""
        logger.info("asr engine close requested")

    def join(self, timeout: float | None = None) -> None:
        """Join background engine thread."""
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
            from websockets.typing import Subprotocol
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("websockets package is required") from exc

        url = self._cfg.asr_ws_url
        logger.info("asr websocket connecting url=%s", url)
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            max_size=2**22,
            subprotocols=[Subprotocol("binary")],
        ) as ws:
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
                exc = task.exception()
                if exc is not None:
                    raise exc

    async def _sender(self, ws: Any) -> None:
        await ws.send(json.dumps(self._build_ws_config(is_speaking=True)))
        while not self._stop_event.is_set() or not self._in_queue.empty():
            frame = await asyncio.to_thread(self._get_frame, _FRAME_POLL_TIMEOUT_S)
            if frame is None:
                continue
            await ws.send(frame.data_int16)
        await ws.send(json.dumps(self._build_ws_config(is_speaking=False)))

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
            put_nowait_or_drop(
                self._final_queue,
                event,
                logger=logger,
                warning=f"asr final queue full; dropping segment_id={segment_id}",
            )

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

    def _build_ws_config(self, *, is_speaking: bool) -> dict[str, Any]:
        return {
            "mode": "2pass",
            "chunk_size": [5, 10, 5],
            "chunk_interval": 10,
            "encoder_chunk_look_back": 4,
            "decoder_chunk_look_back": 1,
            "audio_fs": self._cfg.sample_rate,
            "wav_name": "microphone",
            "is_speaking": is_speaking,
        }
