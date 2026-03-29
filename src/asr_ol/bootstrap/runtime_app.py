"""Application runtime composition root and lifecycle orchestration."""

from __future__ import annotations

import logging
import queue
import threading
import time

from asr_ol.modules.capture.public import build_capture_module
from asr_ol.modules.capture.infrastructure.openwakeword_worker import OpenWakeWordWorker
from asr_ol.modules.capture.infrastructure.silero_worker import SileroVadWorker
from asr_ol.modules.injection.public import build_injection_module
from asr_ol.modules.runtime.infrastructure.audio_bus import AudioBus
from asr_ol.modules.runtime.infrastructure.audio_capture import SoundDeviceAudioSource
from asr_ol.modules.runtime.infrastructure.lifecycle import Worker, WorkerHandle
from asr_ol.modules.storage.public import build_storage_module
from asr_ol.modules.transcription.public import build_transcription_module
from asr_ol.shared.config import AppConfig
from asr_ol.shared.events import (
    AsrFinalEvent,
    CaptureCommand,
    ProcessedFrame,
    RawAudioChunk,
    StorageRecord,
    VadEvent,
    WakeEvent,
)

logger = logging.getLogger(__name__)


_RUN_FOREVER_POLL_S = 0.2


def build_wake_worker(
    *,
    in_queue: queue.Queue[ProcessedFrame],
    out_queue: queue.Queue[WakeEvent],
    stop_event: threading.Event,
    cfg: AppConfig,
) -> OpenWakeWordWorker:
    """Build the wake detection worker."""
    return OpenWakeWordWorker(
        in_queue=in_queue,
        out_queue=out_queue,
        stop_event=stop_event,
        rules=cfg.enabled_wake_rules,
    )


def build_vad_worker(
    *,
    in_queue: queue.Queue[ProcessedFrame],
    out_queue: queue.Queue[VadEvent],
    stop_event: threading.Event,
    cfg: AppConfig,
) -> SileroVadWorker:
    """Build the VAD worker."""
    return SileroVadWorker(
        in_queue=in_queue,
        out_queue=out_queue,
        stop_event=stop_event,
        speech_threshold=cfg.vad_speech_threshold,
        silence_ms=cfg.vad_silence_ms,
    )


class AppRuntime:
    """Assemble and coordinate the full audio-to-action runtime pipeline."""

    def __init__(self, cfg: AppConfig):
        """Create queues, components, workers, and lifecycle plans."""
        self._cfg = cfg
        self.stop_event = threading.Event()
        self._fatal_error: str | None = None

        self.raw_queue: queue.Queue[RawAudioChunk] = queue.Queue(maxsize=cfg.max_queue_size)
        self.wake_audio_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self.vad_audio_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
        self.asr_audio_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)

        self.wake_event_queue: queue.Queue[WakeEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self.vad_event_queue: queue.Queue[VadEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self.asr_event_bus: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self.capture_asr_queue: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
        self.capture_cmd_queue: queue.Queue[CaptureCommand] = queue.Queue(
            maxsize=cfg.max_queue_size
        )

        self.storage_queue: queue.Queue[StorageRecord] = queue.Queue(maxsize=cfg.max_queue_size)

        self.audio_source = SoundDeviceAudioSource(out_queue=self.raw_queue, cfg=cfg)
        self.audio_bus = AudioBus(
            raw_queue=self.raw_queue,
            wake_queue=self.wake_audio_queue,
            vad_queue=self.vad_audio_queue,
            asr_queue=self.asr_audio_queue,
            stop_event=self.stop_event,
        )

        self.wake_worker = build_wake_worker(
            in_queue=self.wake_audio_queue,
            out_queue=self.wake_event_queue,
            stop_event=self.stop_event,
            cfg=cfg,
        )
        self.vad_worker = build_vad_worker(
            in_queue=self.vad_audio_queue,
            out_queue=self.vad_event_queue,
            stop_event=self.stop_event,
            cfg=cfg,
        )

        self.asr_worker = build_transcription_module(
            in_queue=self.asr_audio_queue,
            capture_queue=self.capture_asr_queue,
            storage_queue=self.storage_queue,
            stop_event=self.stop_event,
            cfg=cfg,
        )
        self.asr_engine = getattr(self.asr_worker, "_engine", None)

        self.capture_worker = build_capture_module(
            wake_queue=self.wake_event_queue,
            vad_queue=self.vad_event_queue,
            asr_queue=self.capture_asr_queue,
            downstream_queue=self.capture_cmd_queue,
            storage_queue=self.storage_queue,
            stop_event=self.stop_event,
            cfg=cfg,
        )

        self.injector_worker = build_injection_module(
            in_queue=self.capture_cmd_queue,
            stop_event=self.stop_event,
            cfg=cfg,
        )

        self.storage_worker = build_storage_module(
            in_queue=self.storage_queue,
            stop_event=self.stop_event,
            cfg=cfg,
        )

        self._startup_workers = (
            self._worker_handle("storage_worker", self.storage_worker, 2),
            self._worker_handle("capture_worker", self.capture_worker, 2),
            self._worker_handle("injector_worker", self.injector_worker, 2),
            self._worker_handle("wake_worker", self.wake_worker, 2),
            self._worker_handle("vad_worker", self.vad_worker, 2),
            self._worker_handle("asr_worker", self.asr_worker, 3),
            self._worker_handle("audio_bus", self.audio_bus, 2),
        )
        self._shutdown_workers = (
            self._worker_handle("audio_bus", self.audio_bus, 2),
            self._worker_handle("wake_worker", self.wake_worker, 2),
            self._worker_handle("vad_worker", self.vad_worker, 2),
            self._worker_handle("asr_worker", self.asr_worker, 3),
            self._worker_handle("capture_worker", self.capture_worker, 2),
            self._worker_handle("injector_worker", self.injector_worker, 2),
            self._worker_handle("storage_worker", self.storage_worker, 2),
        )

    @staticmethod
    def _worker_handle(name: str, worker: Worker, join_timeout_s: float) -> WorkerHandle:
        return WorkerHandle(name=name, worker=worker, join_timeout_s=join_timeout_s)

    def _start_workers(self) -> None:
        for handle in self._startup_workers:
            handle.worker.start()

    def _join_workers(self) -> None:
        for handle in self._shutdown_workers:
            handle.worker.join(timeout=handle.join_timeout_s)

    def _find_unhealthy_workers(self) -> tuple[str, ...]:
        return tuple(
            handle.name for handle in self._startup_workers if not handle.worker.is_alive()
        )

    @property
    def fatal_error(self) -> str | None:
        """Return fatal runtime error message when one has occurred."""
        return self._fatal_error

    def start(self) -> None:
        """Start all workers and audio capture in dependency-safe order."""
        logger.info("runtime starting")
        self._start_workers()
        self.audio_source.start()
        logger.info("runtime started")

    def run_forever(self) -> None:
        """Block until shutdown while monitoring worker health."""
        while not self.stop_event.is_set():
            unhealthy_workers = self._find_unhealthy_workers()
            if unhealthy_workers:
                names = ", ".join(unhealthy_workers)
                self._fatal_error = f"worker stopped unexpectedly: {names}"
                logger.error(self._fatal_error)
                self.stop_event.set()
                return
            time.sleep(_RUN_FOREVER_POLL_S)

    def stop(self) -> None:
        """Trigger graceful shutdown and join all workers."""
        logger.info("runtime stopping")
        self.stop_event.set()

        try:
            self.audio_source.stop()
        except Exception:
            logger.exception("audio source stop failed")

        self._join_workers()
        logger.info("runtime stopped")


__all__ = ["AppRuntime"]
