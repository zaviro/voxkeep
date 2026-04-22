"""Qwen3-ASR vLLM realtime websocket transcription adapter."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import queue
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, cast

from voxkeep.modules.transcription.application.backend_events import BackendTranscriptEvent
from voxkeep.modules.transcription.contracts import TranscriptionBackendEvent
from voxkeep.shared.config import AsrConfig
from voxkeep.shared.events import ProcessedFrame
from voxkeep.shared.interfaces import ASREngine
from voxkeep.shared.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)

_FRAME_POLL_TIMEOUT_S = 0.1
_MIN_OVERLAP_WORDS = 4
_MIN_SUFFIX_REPLACEMENT_WORDS = 6
_VOICE_ENERGY_THRESHOLD = 0.01
_LANGUAGE_TAG_RE = re.compile(r"language\s+[A-Za-z_-]+\s*<asr_text>", re.IGNORECASE)


@dataclass(slots=True)
class _SegmentWindow:
    start_ts: float
    end_ts: float


class QwenVllmEngine(ASREngine):
    """ASR engine implementation backed by an externally managed Qwen vLLM service."""

    def __init__(self, cfg: AsrConfig, stop_event: threading.Event):
        """Initialize vLLM engine queues and lifecycle state."""
        self._cfg = cfg
        self._stop_event = stop_event
        self._in_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self._final_queue: queue.Queue[BackendTranscriptEvent] = queue.Queue(
            maxsize=cfg.max_queue_size
        )

        self._thread: threading.Thread | None = None
        self._segment_windows: deque[_SegmentWindow] = deque()
        self._current_partial_text = ""

    @property
    def final_queue(self) -> queue.Queue[TranscriptionBackendEvent]:
        """Return queue receiving finalized transcript events."""
        return cast(queue.Queue[TranscriptionBackendEvent], self._final_queue)

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
        backoff = self._cfg.reconnect_initial_s
        max_backoff = self._cfg.reconnect_max_s

        while not self._stop_event.is_set():
            try:
                await self._run_session()
                backoff = self._cfg.reconnect_initial_s
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
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("websockets package is required") from exc

        if not self._cfg.qwen_realtime:
            raise RuntimeError(
                "qwen_vllm requires asr.qwen.realtime=true; non-realtime mode is not implemented"
            )

        self._segment_windows.clear()
        self._current_partial_text = ""

        async with websockets.connect(
            self._endpoint_url(),
            ping_interval=20,
            ping_timeout=20,
            max_size=2**22,
        ) as ws:
            created = json.loads(await ws.recv())
            if created.get("type") != "session.created":
                raise RuntimeError(f"unexpected realtime handshake: {created}")

            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "model": self._model_name(),
                    }
                )
            )

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
        utterance_start_ts: float | None = None
        utterance_end_ts: float | None = None
        silence_started_at: float | None = None
        has_voiced_audio = False
        silence_threshold_s = self._cfg.vad_silence_ms / 1000.0

        while not self._stop_event.is_set() or not self._in_queue.empty():
            frame = await asyncio.to_thread(self._get_frame, _FRAME_POLL_TIMEOUT_S)
            if frame is None:
                continue

            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(frame.data_int16).decode("ascii"),
                    }
                )
            )

            voiced = self._is_voiced(frame)
            if voiced:
                if utterance_start_ts is None:
                    utterance_start_ts = frame.ts_start
                utterance_end_ts = frame.ts_end
                silence_started_at = None
                has_voiced_audio = True
                continue

            if not has_voiced_audio:
                continue

            utterance_end_ts = frame.ts_end
            if silence_started_at is None:
                silence_started_at = frame.ts_start

            if frame.ts_end - silence_started_at < silence_threshold_s:
                continue

            await self._commit_utterance(
                ws,
                start_ts=utterance_start_ts,
                end_ts=utterance_end_ts,
            )
            utterance_start_ts = None
            utterance_end_ts = None
            silence_started_at = None
            has_voiced_audio = False

        if has_voiced_audio and utterance_start_ts is not None and utterance_end_ts is not None:
            await self._commit_utterance(
                ws,
                start_ts=utterance_start_ts,
                end_ts=utterance_end_ts,
            )

    async def _receiver(self, ws: Any) -> None:
        async for raw in ws:
            event = self._parse_stream_event(raw)
            if event is None:
                continue
            put_nowait_or_drop(
                self._final_queue,
                event,
                logger=logger,
                warning=f"qwen_vllm final queue full; dropping segment_id={event.segment_id}",
            )

    async def _commit_utterance(self, ws: Any, *, start_ts: float, end_ts: float) -> None:
        self._segment_windows.append(_SegmentWindow(start_ts=start_ts, end_ts=end_ts))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))

    def _parse_stream_event(self, raw: Any) -> BackendTranscriptEvent | None:
        payload = self._normalize_payload(raw)
        if payload is None:
            return None

        event_type = str(payload.get("type") or "")
        if event_type == "transcription.delta":
            self._current_partial_text += str(payload.get("delta") or "")
            return None
        if event_type != "transcription.done" and not self._is_final_payload(payload):
            return None

        text = self._clean_realtime_text(self._extract_text(payload))
        self._current_partial_text = ""
        if not text:
            return None

        now = time.time()
        window = self._segment_windows.popleft() if self._segment_windows else None
        start_ts = float(payload.get("start") or payload.get("start_time") or now)
        end_ts = float(payload.get("end") or payload.get("end_time") or now)
        if window is not None:
            start_ts = window.start_ts
            end_ts = window.end_ts
        segment_id = str(payload.get("segment_id") or payload.get("id") or uuid.uuid4())

        return BackendTranscriptEvent(
            segment_id=segment_id,
            text=text,
            start_ts=start_ts,
            end_ts=end_ts,
            event_type="final",
        )

    def _endpoint_url(self) -> str:
        return self._cfg.ws_url

    def _model_name(self) -> str:
        return self._cfg.qwen_model

    def _get_frame(self, timeout: float) -> ProcessedFrame | None:
        try:
            return self._in_queue.get(timeout=timeout)
        except queue.Empty:
            return None

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
        if isinstance(delta, str):
            return delta
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
        if payload.get("type") in {"final", "transcription.done"}:
            return True
        if payload.get("event") == "final":
            return True
        return False

    @staticmethod
    def _is_voiced(frame: ProcessedFrame) -> bool:
        energy = float(abs(frame.pcm_f32).mean()) if len(frame.pcm_f32) > 0 else 0.0
        return energy >= _VOICE_ENERGY_THRESHOLD

    @classmethod
    def _clean_realtime_text(cls, text: str) -> str:
        cleaned = _LANGUAGE_TAG_RE.sub("", text)
        segments = [cls._normalize_segment(part) for part in cleaned.splitlines()]
        merged: list[str] = []
        for segment in segments:
            if not segment:
                continue
            cls._merge_segment(merged, segment)
        return " ".join(merged).strip()

    @staticmethod
    def _normalize_segment(text: str) -> str:
        return " ".join(text.replace("<asr_text>", " ").split()).strip()

    @classmethod
    def _merge_segment(cls, merged: list[str], segment: str) -> None:
        if not merged:
            merged.append(segment)
            return

        previous = merged[-1]
        prev_words = previous.split()
        seg_words = segment.split()
        common_suffix = cls._common_suffix_words(prev_words, seg_words)
        if common_suffix >= _MIN_SUFFIX_REPLACEMENT_WORDS:
            merged[-1] = segment
            return

        overlap = cls._overlap_words(prev_words, seg_words)
        if overlap >= _MIN_OVERLAP_WORDS:
            remainder = " ".join(seg_words[overlap:]).strip()
            if remainder:
                merged[-1] = f"{previous} {remainder}".strip()
            return

        if segment in previous:
            return
        if previous in segment:
            merged[-1] = segment
            return

        merged.append(segment)

    @staticmethod
    def _overlap_words(left: list[str], right: list[str]) -> int:
        max_len = min(len(left), len(right))
        for size in range(max_len, 0, -1):
            if left[-size:] == right[:size]:
                return size
        return 0

    @staticmethod
    def _common_suffix_words(left: list[str], right: list[str]) -> int:
        max_len = min(len(left), len(right))
        for size in range(max_len, 0, -1):
            if left[-size:] == right[-size:]:
                return size
        return 0


__all__ = ["QwenVllmEngine"]
