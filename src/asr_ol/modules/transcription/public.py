"""Public entrypoints for the transcription module."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Protocol

from asr_ol.shared.config import AppConfig
from asr_ol.shared.events import AsrFinalEvent, ProcessedFrame, StorageRecord
from asr_ol.shared.queue_utils import put_nowait_or_drop
from asr_ol.modules.transcription.application.transcription_service import (
    to_processed_frame,
    to_transcript_finalized,
)
from asr_ol.modules.transcription.infrastructure.asr_worker import AsrWorker as LegacyAsrWorker
from asr_ol.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine
from asr_ol.shared.types import AudioFrame, TranscriptFinalized

logger = logging.getLogger(__name__)
_QUEUE_GET_TIMEOUT_S = 0.1


class TranscriptionModule(Protocol):
    """Public API exposed by the transcription module."""

    def start(self) -> None:
        """Start module resources."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop module resources."""
        raise NotImplementedError

    def submit_audio(self, frame: AudioFrame) -> None:
        """Submit one audio frame into the transcription pipeline."""
        raise NotImplementedError

    def subscribe_transcript_finalized(
        self, handler: Callable[[TranscriptFinalized], None]
    ) -> None:
        """Subscribe to final transcript events."""
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        """Join module resources."""
        raise NotImplementedError

    def is_alive(self) -> bool:
        """Report whether module resources are alive."""
        raise NotImplementedError


class WorkerTranscriptionModule:
    """Public transcription module backed by the legacy engine and worker."""

    def __init__(
        self,
        *,
        capture_queue: queue.Queue[AsrFinalEvent],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        cfg: AppConfig,
        in_queue: queue.Queue[ProcessedFrame] | None = None,
    ) -> None:
        """Create a transcription module backed by existing implementations."""
        self._in_queue = in_queue or queue.Queue(maxsize=cfg.max_queue_size)
        self._public_out_queue: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self._stop_event = stop_event
        self._handlers: list[Callable[[TranscriptFinalized], None]] = []
        self._fanout_thread: threading.Thread | None = None

        self._engine = FunAsrWsEngine(cfg=cfg, stop_event=stop_event)
        self._final_in_queue = self._engine.final_queue
        self._worker = LegacyAsrWorker(
            in_queue=self._in_queue,
            final_in_queue=self._final_in_queue,
            out_queue=self._public_out_queue,
            capture_queue=capture_queue,
            storage_queue=storage_queue,
            stop_event=stop_event,
            engine=self._engine,
            store_final_only=cfg.store_final_only,
        )

    def start(self) -> None:
        """Start the underlying worker and fanout bridge."""
        if self._fanout_thread is None:
            self._fanout_thread = threading.Thread(
                target=self._fanout_loop,
                name="transcription_public_fanout",
                daemon=True,
            )
            self._fanout_thread.start()
        self._worker.start()

    def stop(self) -> None:
        """Expose a symmetric lifecycle hook for the runtime module."""
        self._stop_event.set()

    def submit_audio(self, frame: AudioFrame) -> None:
        """Submit one audio frame into the transcription pipeline."""
        processed = to_processed_frame(frame)
        put_nowait_or_drop(
            self._in_queue,
            processed,
            logger=logger,
            warning=f"transcription input queue full; dropping frame_id={processed.frame_id}",
        )

    def subscribe_transcript_finalized(
        self, handler: Callable[[TranscriptFinalized], None]
    ) -> None:
        """Subscribe to final transcript events."""
        self._handlers.append(handler)

    def join(self, timeout: float | None = None) -> None:
        """Join worker and fanout resources."""
        self._worker.join(timeout=timeout)
        if self._fanout_thread is not None:
            self._fanout_thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Report whether worker and fanout resources are alive."""
        fanout_alive = self._fanout_thread is not None and self._fanout_thread.is_alive()
        return self._worker.is_alive() or fanout_alive

    def _fanout_loop(self) -> None:
        while not self._stop_event.is_set() or not self._public_out_queue.empty():
            try:
                event = self._public_out_queue.get(timeout=_QUEUE_GET_TIMEOUT_S)
            except queue.Empty:
                continue
            public_event = to_transcript_finalized(event)
            for handler in self._handlers:
                handler(public_event)


def build_transcription_module(
    *,
    capture_queue: queue.Queue[AsrFinalEvent],
    storage_queue: queue.Queue[StorageRecord],
    stop_event: threading.Event,
    cfg: AppConfig,
    in_queue: queue.Queue[ProcessedFrame] | None = None,
) -> TranscriptionModule:
    """Build the transcription module public entrypoint."""
    return WorkerTranscriptionModule(
        capture_queue=capture_queue,
        storage_queue=storage_queue,
        stop_event=stop_event,
        cfg=cfg,
        in_queue=in_queue,
    )


__all__ = ["TranscriptionModule", "WorkerTranscriptionModule", "build_transcription_module"]
