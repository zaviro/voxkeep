from __future__ import annotations

import logging
import queue
import threading

from asr_ol.core.events import CaptureCommand
from asr_ol.tools.injector.base import Injector

logger = logging.getLogger(__name__)


class InjectorWorker:
    def __init__(
        self,
        in_queue: queue.Queue[CaptureCommand],
        stop_event: threading.Event,
        injector: Injector,
    ) -> None:
        self._in_queue = in_queue
        self._stop_event = stop_event
        self._injector = injector
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="injector_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        logger.info("injector worker started")
        while not self._stop_event.is_set() or not self._in_queue.empty():
            try:
                cmd = self._in_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            ok = self._injector.inject(cmd.text)
            if ok:
                logger.info("injected session_id=%s text=%s", cmd.session_id, cmd.text)
            else:
                logger.warning("injection failed session_id=%s text=%s", cmd.session_id, cmd.text)

        logger.info("injector worker stopped")
