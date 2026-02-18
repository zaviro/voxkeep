from __future__ import annotations

from datetime import datetime, timezone
import logging
import queue
import threading
import time

from asr_ol.agents.capture_fsm import CaptureFSM
from asr_ol.core.events import AsrFinalEvent, CaptureCommand, StorageRecord, VadEvent, WakeEvent

logger = logging.getLogger(__name__)


class CaptureWorker:
    def __init__(
        self,
        wake_queue: queue.Queue[WakeEvent],
        vad_queue: queue.Queue[VadEvent],
        asr_queue: queue.Queue[AsrFinalEvent],
        out_queue: queue.Queue[CaptureCommand],
        storage_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        fsm: CaptureFSM,
    ) -> None:
        self._wake_queue = wake_queue
        self._vad_queue = vad_queue
        self._asr_queue = asr_queue
        self._out_queue = out_queue
        self._storage_queue = storage_queue
        self._stop_event = stop_event
        self._fsm = fsm
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="capture_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

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
                time.sleep(0.01)

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
            self._fsm.on_asr_final(asr_event)
            handled = True
        except queue.Empty:
            pass

        try:
            vad_event = self._vad_queue.get_nowait()
            command = self._fsm.on_vad(vad_event)
            if command is not None:
                self._emit_capture(command)
            handled = True
        except queue.Empty:
            pass

        return handled

    def _emit_capture(self, command: CaptureCommand) -> None:
        try:
            self._out_queue.put_nowait(command)
            logger.info("capture finalized session_id=%s text=%s", command.session_id, command.text)
        except queue.Full:
            logger.warning("capture out queue full; dropping session_id=%s", command.session_id)
            return

        record = StorageRecord(
            source="capture",
            text=command.text,
            start_ts=command.start_ts,
            end_ts=command.end_ts,
            is_final=True,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        try:
            self._storage_queue.put_nowait(record)
        except queue.Full:
            logger.warning(
                "storage queue full; dropping capture storage session_id=%s", command.session_id
            )
