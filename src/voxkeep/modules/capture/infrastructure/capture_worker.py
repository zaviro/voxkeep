"""Background worker for wake-triggered capture orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import queue
import threading
import time

from voxkeep.shared.events import AsrFinalEvent, CaptureCommand, StorageRecord, VadEvent, WakeEvent
from voxkeep.shared.queue_utils import put_nowait_or_drop
from voxkeep.modules.capture.application.transcript_extractor import TranscriptExtractor
from voxkeep.modules.capture.domain.capture_fsm import CaptureFSM, CaptureWindow

logger = logging.getLogger(__name__)


_IDLE_SLEEP_S = 0.01


class CaptureWorker:
    """Consume wake/VAD/ASR events and emit one-shot capture commands."""

    def __init__(
        self,
        wake_queue: queue.Queue[WakeEvent],
        vad_queue: queue.Queue[VadEvent],
        asr_queue: queue.Queue[AsrFinalEvent],
        out_queue: queue.Queue[CaptureCommand],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        fsm: CaptureFSM,
        transcript_extractor: TranscriptExtractor,
        action_by_keyword: dict[str, str],
        default_action: str,
    ) -> None:
        """Create worker dependencies and routing rules."""
        self._wake_queue = wake_queue
        self._vad_queue = vad_queue
        self._asr_queue = asr_queue
        self._out_queue = out_queue
        self._storage_queue = storage_queue
        self._stop_event = stop_event
        self._fsm = fsm
        self._extractor = transcript_extractor
        self._action_by_keyword = dict(action_by_keyword)
        self._default_action = default_action
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background capture worker thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="capture_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        """Join the background capture worker thread."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Return whether the worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        logger.info("capture worker started")
        while (
            not self._stop_event.is_set()
            or not self._wake_queue.empty()
            or not self._vad_queue.empty()
            or not self._asr_queue.empty()
        ):
            had_event = self._consume_once()
            self._fsm.tick()
            if not had_event:
                time.sleep(_IDLE_SLEEP_S)

        logger.info("capture worker stopped")

    def _consume_once(self) -> bool:
        handled = False

        try:
            wake_event = self._wake_queue.get_nowait()
            self._fsm.on_wake(wake_event)
            handled = True
        except queue.Empty:
            pass

        try:
            asr_event = self._asr_queue.get_nowait()
            self._extractor.on_asr_final(asr_event)
            handled = True
        except queue.Empty:
            pass

        try:
            vad_event = self._vad_queue.get_nowait()
            window = self._fsm.on_vad(vad_event)
            if window is not None:
                self._emit_capture(window)
            handled = True
        except queue.Empty:
            pass

        return handled

    def _emit_capture(self, window: CaptureWindow) -> None:
        start_ts = window.start_ts
        end_ts = window.end_ts
        keyword = window.keyword
        session_id = window.session_id
        text = self._extractor.extract(start_ts=start_ts, end_ts=end_ts)
        if not text:
            logger.info("capture empty session_id=%s keyword=%s", session_id, keyword)
            return

        action = self._action_by_keyword.get(keyword, self._default_action)
        command = CaptureCommand(
            session_id=session_id,
            keyword=keyword,
            action=action,
            text=text,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        if put_nowait_or_drop(
            self._out_queue,
            command,
            logger=logger,
            warning=f"capture out queue full; dropping session_id={command.session_id}",
        ):
            logger.info(
                "capture finalized session_id=%s keyword=%s action=%s text=%s",
                command.session_id,
                command.keyword,
                command.action,
                command.text,
            )
        else:
            return

        record = StorageRecord(
            source="capture",
            text=command.text,
            start_ts=command.start_ts,
            end_ts=command.end_ts,
            is_final=True,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        put_nowait_or_drop(
            self._storage_queue,
            record,
            logger=logger,
            warning=f"storage queue full; dropping capture storage session_id={command.session_id}",
        )
