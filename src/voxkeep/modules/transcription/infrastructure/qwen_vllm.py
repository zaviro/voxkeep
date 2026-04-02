"""Qwen3-ASR vLLM streaming transcription adapter."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import queue
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.shared.config import AppConfig
from voxkeep.shared.events import ProcessedFrame
from voxkeep.shared.interfaces import ASREngine
from voxkeep.shared.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)

_FRAME_POLL_TIMEOUT_S = 0.1


@dataclass(slots=True)
class _AsyncLineStream:
    """Async iterator wrapper for streamed backend responses."""

    lines: list[Any]

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for line in self.lines:
            yield line


class QwenVllmEngine(ASREngine):
    """ASR engine implementation backed by an externally managed Qwen vLLM service."""

    def __init__(self, cfg: AppConfig, stop_event: threading.Event):
        """Initialize engine queues and lifecycle state."""
        self._cfg = cfg
        self._stop_event = stop_event
        self._in_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self._final_queue: queue.Queue[BackendTranscriptEvent] = queue.Queue(
            maxsize=cfg.max_queue_size
        )
        self._thread: threading.Thread | None = None

    @property
    def final_queue(self) -> queue.Queue[BackendTranscriptEvent]:
        """Return queue receiving finalized transcript events."""
        return self._final_queue

    def start(self) -> None:
        """Start the background worker thread once."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run_thread, name="qwen_vllm_engine", daemon=True
        )
        self._thread.start()

    def submit_frame(self, frame: ProcessedFrame) -> None:
        """Submit one processed audio frame for recognition."""
        put_nowait_or_drop(
            self._in_queue,
            frame,
            logger=logger,
            warning=f"qwen_vllm input queue full; dropping frame_id={frame.frame_id}",
        )

    def close(self) -> None:
        """Log a close request; lifecycle is driven by the stop event."""
        logger.info("qwen_vllm engine close requested")

    def join(self, timeout: float | None = None) -> None:
        """Join the background worker thread."""
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
                logger.warning(
                    "qwen_vllm session error endpoint=%s error=%s reconnect_in=%.1fs",
                    self._endpoint_url(),
                    exc,
                    backoff,
                )
                should_stop = await asyncio.to_thread(self._stop_event.wait, backoff)
                if should_stop:
                    break
                backoff = min(max_backoff, backoff * 2)

        logger.info("qwen_vllm engine stopped")

    async def _run_session(self) -> None:
        while not self._stop_event.is_set() or not self._in_queue.empty():
            frame = await asyncio.to_thread(self._get_frame, _FRAME_POLL_TIMEOUT_S)
            if frame is None:
                continue
            try:
                lines = await asyncio.to_thread(self._post_frame, frame)
                await self._receiver(_AsyncLineStream(lines))
            except Exception as exc:
                logger.warning(
                    "qwen_vllm request failed endpoint=%s frame_id=%s error=%s",
                    self._endpoint_url(),
                    frame.frame_id,
                    exc,
                )
                raise

    async def _receiver(self, stream: Any) -> None:
        async for raw in stream:
            event = self._parse_stream_event(raw)
            if event is None:
                continue
            put_nowait_or_drop(
                self._final_queue,
                event,
                logger=logger,
                warning=f"qwen_vllm final queue full; dropping segment_id={event.segment_id}",
            )

    def _parse_stream_event(self, raw: Any) -> BackendTranscriptEvent | None:
        payload = self._normalize_payload(raw)
        if payload is None:
            return None
        if not self._is_final_payload(payload):
            logger.debug("qwen_vllm partial event discarded payload=%s", payload)
            return None

        text = self._extract_text(payload).strip()
        if not text:
            return None

        now = time.time()
        start_ts = float(payload.get("start") or payload.get("start_time") or now)
        end_ts = float(payload.get("end") or payload.get("end_time") or now)
        segment_id = str(payload.get("segment_id") or payload.get("id") or uuid.uuid4())

        return BackendTranscriptEvent(
            segment_id=segment_id,
            text=text,
            start_ts=start_ts,
            end_ts=end_ts,
            event_type="final",
        )

    def _post_frame(self, frame: ProcessedFrame) -> list[Any]:
        request_body = json.dumps(self._build_request_payload(frame)).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint_url(),
            data=request_body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self._cfg.asr_reconnect_max_s) as response:
            return [line.decode("utf-8", errors="replace") for line in response]

    def _build_request_payload(self, frame: ProcessedFrame) -> dict[str, Any]:
        return {
            "audio": base64.b64encode(frame.data_int16).decode("ascii"),
            "frame_id": frame.frame_id,
            "sample_rate": frame.sample_rate,
            "start": frame.ts_start,
            "end": frame.ts_end,
        }

    def _get_frame(self, timeout: float) -> ProcessedFrame | None:
        try:
            return self._in_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _endpoint_url(self) -> str:
        schema = "https" if self._cfg.asr_external_use_ssl else "http"
        return f"{schema}://{self._cfg.asr_external_host}:{self._cfg.asr_external_port}{self._cfg.asr_external_path}"

    @staticmethod
    def _normalize_payload(raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if not isinstance(raw, str):
            return None
        raw = raw.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        text = payload.get("text")
        if isinstance(text, str):
            return text
        delta = payload.get("delta")
        if isinstance(delta, dict):
            nested = delta.get("text")
            if isinstance(nested, str):
                return nested
        result = payload.get("result")
        if isinstance(result, str):
            return result
        return ""

    @staticmethod
    def _is_final_payload(payload: dict[str, Any]) -> bool:
        if payload.get("is_final") is True:
            return True
        finish_reason = payload.get("finish_reason")
        if finish_reason in {"stop", "final", "completed"}:
            return True
        if payload.get("type") == "final":
            return True
        if payload.get("event") == "final":
            return True
        return False


__all__ = ["QwenVllmEngine"]
