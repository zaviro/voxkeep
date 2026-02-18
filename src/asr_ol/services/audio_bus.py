from __future__ import annotations

import logging
import queue
import threading

from asr_ol.infra.audio.preprocess import Preprocessor
from asr_ol.core.events import ProcessedFrame, RawAudioChunk

logger = logging.getLogger(__name__)


class AudioBus:
    def __init__(
        self,
        raw_queue: queue.Queue[RawAudioChunk],
        wake_queue: queue.Queue[ProcessedFrame],
        vad_queue: queue.Queue[ProcessedFrame],
        asr_queue: queue.Queue[ProcessedFrame],
        stop_event: threading.Event,
    ) -> None:
        self._raw_queue = raw_queue
        self._wake_queue = wake_queue
        self._vad_queue = vad_queue
        self._asr_queue = asr_queue
        self._stop_event = stop_event
        self._preprocessor = Preprocessor()
        self._thread: threading.Thread | None = None
        self._dropped = {"wake": 0, "vad": 0, "asr": 0}

    @property
    def dropped(self) -> dict[str, int]:
        return dict(self._dropped)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="audio_bus", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _fanout_put(self, q: queue.Queue[ProcessedFrame], frame: ProcessedFrame, name: str) -> None:
        try:
            q.put_nowait(frame)
        except queue.Full:
            self._dropped[name] += 1

    def run_once(self, timeout: float = 0.1) -> None:
        try:
            raw = self._raw_queue.get(timeout=timeout)
        except queue.Empty:
            return

        frame = self._preprocessor.process(raw)
        self._fanout_put(self._wake_queue, frame, "wake")
        self._fanout_put(self._vad_queue, frame, "vad")
        self._fanout_put(self._asr_queue, frame, "asr")

    def _run(self) -> None:
        logger.info("audio bus started")
        while not self._stop_event.is_set() or not self._raw_queue.empty():
            self.run_once(timeout=0.1)
        logger.info("audio bus stopped dropped=%s", self._dropped)
