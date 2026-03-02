from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Protocol

from asr_ol.infra.asr.funasr_ws import FunAsrWsEngine
from asr_ol.services.asr_worker import AsrWorker
from asr_ol.services.audio_bus import AudioBus
from asr_ol.services.lifecycle import Worker, WorkerHandle
from asr_ol.infra.audio.audio_capture import SoundDeviceAudioSource
from asr_ol.agents.capture_fsm import CaptureFSM
from asr_ol.agents.capture_worker import CaptureWorker
from asr_ol.agents.transcript_extractor import InMemoryTranscriptExtractor
from asr_ol.core.config import AppConfig
from asr_ol.core.events import (
    AsrFinalEvent,
    CaptureCommand,
    ProcessedFrame,
    RawAudioChunk,
    StorageRecord,
    VadEvent,
    WakeEvent,
)
from asr_ol.tools.injector.factory import build_injector
from asr_ol.services.injector_worker import InjectorWorker
from asr_ol.infra.storage.storage_worker import StorageWorker
from asr_ol.infra.vad.silero_worker import SileroVadWorker
from asr_ol.infra.wake.openwakeword_worker import OpenWakeWordWorker

logger = logging.getLogger(__name__)


class AudioSourceLike(Protocol):
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class AppRuntime:
    def __init__(self, cfg: AppConfig):
        self._cfg = cfg
        self.stop_event = threading.Event()

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

        self.wake_worker = OpenWakeWordWorker(
            in_queue=self.wake_audio_queue,
            out_queue=self.wake_event_queue,
            stop_event=self.stop_event,
            rules=cfg.enabled_wake_rules,
        )
        self.vad_worker = SileroVadWorker(
            in_queue=self.vad_audio_queue,
            out_queue=self.vad_event_queue,
            stop_event=self.stop_event,
            speech_threshold=cfg.vad_speech_threshold,
            silence_ms=cfg.vad_silence_ms,
        )

        self.asr_engine = FunAsrWsEngine(cfg=cfg, stop_event=self.stop_event)
        self.asr_worker = AsrWorker(
            in_queue=self.asr_audio_queue,
            final_in_queue=self.asr_engine.final_queue,
            out_queue=self.asr_event_bus,
            capture_queue=self.capture_asr_queue,
            storage_queue=self.storage_queue,
            stop_event=self.stop_event,
            engine=self.asr_engine,
            store_final_only=cfg.store_final_only,
        )

        self.capture_fsm = CaptureFSM(
            pre_roll_ms=cfg.pre_roll_ms, armed_timeout_ms=cfg.armed_timeout_ms
        )
        self.transcript_extractor = InMemoryTranscriptExtractor()
        self.capture_worker = CaptureWorker(
            wake_queue=self.wake_event_queue,
            vad_queue=self.vad_event_queue,
            asr_queue=self.capture_asr_queue,
            out_queue=self.capture_cmd_queue,
            storage_queue=self.storage_queue,
            stop_event=self.stop_event,
            fsm=self.capture_fsm,
            transcript_extractor=self.transcript_extractor,
            action_by_keyword={rule.keyword: rule.action for rule in cfg.enabled_wake_rules},
            default_action="inject_text",
        )

        self.injector_worker = InjectorWorker(
            in_queue=self.capture_cmd_queue,
            stop_event=self.stop_event,
            injector=build_injector(cfg),
            openclaw_command=cfg.openclaw_command,
            openclaw_timeout_s=cfg.openclaw_timeout_s,
        )

        self.storage_worker = StorageWorker(
            in_queue=self.storage_queue,
            stop_event=self.stop_event,
            sqlite_path=cfg.sqlite_path,
            jsonl_debug_path=cfg.jsonl_debug_path,
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

    def start(self) -> None:
        logger.info("runtime starting")
        self._start_workers()
        self.audio_source.start()
        logger.info("runtime started")

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            time.sleep(0.2)

    def stop(self) -> None:
        logger.info("runtime stopping")
        self.stop_event.set()

        # Stop audio source first to prevent new frames from entering the pipeline.
        try:
            self.audio_source.stop()
        except Exception:
            logger.exception("audio source stop failed")

        self._join_workers()
        logger.info("runtime stopped")
