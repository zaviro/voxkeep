# ruff: noqa: D100,D107,D102
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

from asr_ol.shared.interfaces import AudioSource
from asr_ol.shared.config import AppConfig
from asr_ol.shared.events import RawAudioChunk
from asr_ol.shared.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)


class SoundDeviceAudioSource(AudioSource):
    """Single audio input stream. Callback must remain enqueue-only."""

    def __init__(self, out_queue: queue.Queue[RawAudioChunk], cfg: AppConfig):
        self._out_queue = out_queue
        self._cfg = cfg
        self._stream: Any | None = None
        self._dropped_chunks = 0
        self._lock = threading.Lock()

    @property
    def dropped_chunks(self) -> int:
        with self._lock:
            return self._dropped_chunks

    def _on_audio(self, indata: Any, frames: int, _time_info: Any, _status: Any) -> None:
        # Copy and enqueue only. No heavy compute, no I/O, no network calls.
        chunk = RawAudioChunk(
            data=indata.copy().tobytes(),
            frames=frames,
            sample_rate=self._cfg.sample_rate,
            channels=self._cfg.channels,
            ts=time.time(),
        )
        put_nowait_or_drop(self._out_queue, chunk, on_drop=self._increment_dropped_chunks)

    def _increment_dropped_chunks(self) -> None:
        with self._lock:
            self._dropped_chunks += 1

    def start(self) -> None:
        if self._stream is not None:
            return

        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("sounddevice is required for microphone capture") from exc

        self._stream = sd.InputStream(
            samplerate=self._cfg.sample_rate,
            channels=self._cfg.channels,
            blocksize=self._cfg.frame_samples,
            dtype="int16",
            callback=self._on_audio,
        )
        self._stream.start()
        logger.info(
            "audio source started sample_rate=%s channels=%s frame_samples=%s",
            self._cfg.sample_rate,
            self._cfg.channels,
            self._cfg.frame_samples,
        )

    def stop(self) -> None:
        stream = self._stream
        if stream is None:
            return

        self._stream = None
        stream.stop()
        stream.close()
        logger.info("audio source stopped")
