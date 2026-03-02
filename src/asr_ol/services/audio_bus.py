"""Audio bus for preprocessing and fanout to downstream workers."""

from __future__ import annotations

import logging
import queue
import threading

from asr_ol.infra.audio.preprocess import Preprocessor
from asr_ol.core.events import ProcessedFrame, RawAudioChunk
from asr_ol.core.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)


_QUEUE_GET_TIMEOUT_S = 0.1


class AudioBus:
    """Preprocess raw chunks once and fan out frames to three pipelines."""

    def __init__(
        self,
        raw_queue: queue.Queue[RawAudioChunk],
        wake_queue: queue.Queue[ProcessedFrame],
        vad_queue: queue.Queue[ProcessedFrame],
        asr_queue: queue.Queue[ProcessedFrame],
        stop_event: threading.Event,
    ) -> None:
        """Initialize queues and lifecycle primitives."""
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
        """Return per-target dropped frame counters."""
        return dict(self._dropped)

    def start(self) -> None:
        """Start the background fanout thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="audio_bus", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        """Join the background thread."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Return whether the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _fanout_put(self, q: queue.Queue[ProcessedFrame], frame: ProcessedFrame, name: str) -> None:
        if not put_nowait_or_drop(q, frame):
            self._dropped[name] += 1

    def run_once(self, timeout: float = _QUEUE_GET_TIMEOUT_S) -> None:
        """Process one raw chunk and fan it out to wake/VAD/ASR queues."""
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
            self.run_once(timeout=_QUEUE_GET_TIMEOUT_S)
        logger.info("audio bus stopped dropped=%s", self._dropped)
