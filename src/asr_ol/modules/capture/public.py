"""Public entrypoints for the capture module."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Protocol

from asr_ol.agents.capture_fsm import CaptureFSM
from asr_ol.agents.transcript_extractor import InMemoryTranscriptExtractor
from asr_ol.core.config import AppConfig
from asr_ol.core.events import AsrFinalEvent, CaptureCommand, StorageRecord, VadEvent, WakeEvent
from asr_ol.core.queue_utils import put_nowait_or_drop
from asr_ol.modules.capture.application.capture_service import (
    to_asr_final_event,
    to_capture_completed,
    to_vad_event,
    to_wake_event,
)
from asr_ol.modules.capture.infrastructure.capture_worker import (
    CaptureWorker as LegacyCaptureWorker,
)
from asr_ol.shared.types import (
    CaptureCompleted,
    SpeechBoundaryDetected,
    TranscriptFinalized,
    WakeDetected,
)

logger = logging.getLogger(__name__)
_QUEUE_GET_TIMEOUT_S = 0.1


class CaptureModule(Protocol):
    """Public API exposed by the capture module."""

    def start(self) -> None:
        """Start module resources."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop module resources."""
        raise NotImplementedError

    def accept_wake(self, event: WakeDetected) -> None:
        """Accept one wake detection event."""
        raise NotImplementedError

    def accept_vad(self, event: SpeechBoundaryDetected) -> None:
        """Accept one VAD boundary event."""
        raise NotImplementedError

    def accept_transcript(self, event: TranscriptFinalized) -> None:
        """Accept one transcript event."""
        raise NotImplementedError

    def subscribe_capture_completed(self, handler: Callable[[CaptureCompleted], None]) -> None:
        """Subscribe to capture completion events."""
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        """Join module resources."""
        raise NotImplementedError

    def is_alive(self) -> bool:
        """Report whether module resources are alive."""
        raise NotImplementedError


class WorkerCaptureModule:
    """Public capture module backed by the legacy capture worker."""

    def __init__(
        self,
        *,
        downstream_queue: queue.Queue[CaptureCommand],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        cfg: AppConfig,
        wake_queue: queue.Queue[WakeEvent] | None = None,
        vad_queue: queue.Queue[VadEvent] | None = None,
        asr_queue: queue.Queue[AsrFinalEvent] | None = None,
    ) -> None:
        """Create a capture module backed by the worker implementation."""
        self._wake_queue = wake_queue or queue.Queue(maxsize=cfg.max_queue_size)
        self._vad_queue = vad_queue or queue.Queue(maxsize=cfg.max_queue_size)
        self._asr_queue = asr_queue or queue.Queue(maxsize=cfg.max_queue_size)
        self._public_out_queue: queue.Queue[CaptureCommand] = queue.Queue(
            maxsize=cfg.max_queue_size
        )
        self._downstream_queue = downstream_queue
        self._stop_event = stop_event
        self._handlers: list[Callable[[CaptureCompleted], None]] = []
        self._fanout_thread: threading.Thread | None = None

        self._fsm = CaptureFSM(pre_roll_ms=cfg.pre_roll_ms, armed_timeout_ms=cfg.armed_timeout_ms)
        self._extractor = InMemoryTranscriptExtractor()
        self._worker = LegacyCaptureWorker(
            wake_queue=self._wake_queue,
            vad_queue=self._vad_queue,
            asr_queue=self._asr_queue,
            out_queue=self._public_out_queue,
            storage_queue=storage_queue,
            stop_event=stop_event,
            fsm=self._fsm,
            transcript_extractor=self._extractor,
            action_by_keyword={rule.keyword: rule.action for rule in cfg.enabled_wake_rules},
            default_action="inject_text",
        )

    def start(self) -> None:
        """Start the underlying capture worker and fanout bridge."""
        if self._fanout_thread is None:
            self._fanout_thread = threading.Thread(
                target=self._fanout_loop,
                name="capture_public_fanout",
                daemon=True,
            )
            self._fanout_thread.start()
        self._worker.start()

    def stop(self) -> None:
        """Expose a symmetric lifecycle hook for the runtime module."""
        return

    def join(self, timeout: float | None = None) -> None:
        """Join worker and fanout threads."""
        self._worker.join(timeout=timeout)
        if self._fanout_thread is not None:
            self._fanout_thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Report whether worker and fanout resources are alive."""
        fanout_alive = self._fanout_thread is not None and self._fanout_thread.is_alive()
        return self._worker.is_alive() or fanout_alive

    def accept_wake(self, event: WakeDetected) -> None:
        """Accept one wake detection event."""
        put_nowait_or_drop(self._wake_queue, to_wake_event(event), logger=logger)

    def accept_vad(self, event: SpeechBoundaryDetected) -> None:
        """Accept one VAD boundary event."""
        put_nowait_or_drop(self._vad_queue, to_vad_event(event), logger=logger)

    def accept_transcript(self, event: TranscriptFinalized) -> None:
        """Accept one transcript event."""
        put_nowait_or_drop(self._asr_queue, to_asr_final_event(event), logger=logger)

    def subscribe_capture_completed(self, handler: Callable[[CaptureCompleted], None]) -> None:
        """Subscribe to capture completion events."""
        self._handlers.append(handler)

    def _fanout_loop(self) -> None:
        while not self._stop_event.is_set() or not self._public_out_queue.empty():
            try:
                command = self._public_out_queue.get(timeout=_QUEUE_GET_TIMEOUT_S)
            except queue.Empty:
                continue
            put_nowait_or_drop(self._downstream_queue, command, logger=logger)
            event = to_capture_completed(command)
            for handler in self._handlers:
                handler(event)


def build_capture_module(
    *,
    downstream_queue: queue.Queue[CaptureCommand],
    storage_queue: queue.Queue[StorageRecord],
    stop_event: threading.Event,
    cfg: AppConfig,
    wake_queue: queue.Queue[WakeEvent] | None = None,
    vad_queue: queue.Queue[VadEvent] | None = None,
    asr_queue: queue.Queue[AsrFinalEvent] | None = None,
) -> CaptureModule:
    """Build the capture module public entrypoint."""
    return WorkerCaptureModule(
        downstream_queue=downstream_queue,
        storage_queue=storage_queue,
        stop_event=stop_event,
        cfg=cfg,
        wake_queue=wake_queue,
        vad_queue=vad_queue,
        asr_queue=asr_queue,
    )


__all__ = ["CaptureModule", "WorkerCaptureModule", "build_capture_module"]
