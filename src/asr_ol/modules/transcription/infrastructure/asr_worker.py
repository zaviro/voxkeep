"""ASR worker bridging processed audio, engine, and event fanout."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import queue
import threading

from asr_ol.core.asr_engine import ASREngine
from asr_ol.core.events import AsrFinalEvent, ProcessedFrame, StorageRecord
from asr_ol.core.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)


_AUDIO_QUEUE_GET_TIMEOUT_S = 0.05


class AsrWorker:
    """Consume processed audio frames and fan out finalized ASR events."""

    def __init__(
        self,
        in_queue: queue.Queue[ProcessedFrame],
        final_in_queue: queue.Queue[AsrFinalEvent],
        out_queue: queue.Queue[AsrFinalEvent],
        capture_queue: queue.Queue[AsrFinalEvent],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        engine: ASREngine,
        store_final_only: bool,
    ) -> None:
        """Create worker dependencies."""
        self._in_queue = in_queue
        self._final_in_queue = final_in_queue
        self._out_queue = out_queue
        self._capture_queue = capture_queue
        self._storage_queue = storage_queue
        self._stop_event = stop_event
        self._engine = engine
        self._store_final_only = store_final_only
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start engine resources and worker thread once."""
        if self._thread is not None:
            return
        self._engine.start()
        self._thread = threading.Thread(target=self._run, name="asr_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        """Join worker thread and optional engine thread."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        join_fn = getattr(self._engine, "join", None)
        if callable(join_fn):
            join_fn(timeout=timeout)

    def is_alive(self) -> bool:
        """Return whether the worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        logger.info("asr worker started")

        while (
            not self._stop_event.is_set()
            or not self._in_queue.empty()
            or not self._final_in_queue.empty()
        ):
            self._submit_audio_once()
            self._drain_final_events()

        self._engine.close()
        self._drain_final_events()
        logger.info("asr worker stopped")

    def _submit_audio_once(self) -> None:
        try:
            frame = self._in_queue.get(timeout=_AUDIO_QUEUE_GET_TIMEOUT_S)
        except queue.Empty:
            return
        self._engine.submit_frame(frame)

    def _drain_final_events(self) -> None:
        while True:
            try:
                event = self._final_in_queue.get_nowait()
            except queue.Empty:
                return

            self._fanout_event(event)
            if self._store_final_only and not event.is_final:
                continue
            record = StorageRecord(
                source="stream",
                text=event.text,
                start_ts=event.start_ts,
                end_ts=event.end_ts,
                is_final=event.is_final,
                created_at=datetime.now(tz=timezone.utc).isoformat(),
            )
            self._put_maybe_drop(self._storage_queue, record, "storage")

    def _fanout_event(self, event: AsrFinalEvent) -> None:
        self._put_maybe_drop(self._out_queue, event, "asr_event_bus")
        self._put_maybe_drop(self._capture_queue, event, "capture")

    @staticmethod
    def _put_maybe_drop(q: queue.Queue, event: object, name: str) -> None:
        put_nowait_or_drop(
            q, event, logger=logger, warning=f"queue full: dropping event from {name}"
        )
