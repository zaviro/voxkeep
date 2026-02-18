from __future__ import annotations

import logging
import queue
import threading
import time

from asr_ol.infra.asr.funasr_ws import FunAsrWsEngine
from asr_ol.services.asr_worker import AsrWorker
from asr_ol.services.audio_bus import AudioBus
from asr_ol.infra.audio.audio_capture import SoundDeviceAudioSource
from asr_ol.agents.capture_fsm import CaptureFSM
from asr_ol.agents.capture_worker import CaptureWorker
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
            threshold=cfg.wake_threshold,
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
        self.capture_worker = CaptureWorker(
            wake_queue=self.wake_event_queue,
            vad_queue=self.vad_event_queue,
            asr_queue=self.capture_asr_queue,
            out_queue=self.capture_cmd_queue,
            storage_queue=self.storage_queue,
            stop_event=self.stop_event,
            fsm=self.capture_fsm,
        )

        self.injector_worker = InjectorWorker(
            in_queue=self.capture_cmd_queue,
            stop_event=self.stop_event,
            injector=build_injector(cfg),
        )

        self.storage_worker = StorageWorker(
            in_queue=self.storage_queue,
            stop_event=self.stop_event,
            sqlite_path=cfg.sqlite_path,
            jsonl_debug_path=cfg.jsonl_debug_path,
        )

    def start(self) -> None:
        logger.info("runtime starting")
        self.storage_worker.start()
        self.capture_worker.start()
        self.injector_worker.start()
        self.wake_worker.start()
        self.vad_worker.start()
        self.asr_worker.start()
        self.audio_bus.start()
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

        self.audio_bus.join(timeout=2)
        self.wake_worker.join(timeout=2)
        self.vad_worker.join(timeout=2)
        self.asr_worker.join(timeout=3)
        self.capture_worker.join(timeout=2)
        self.injector_worker.join(timeout=2)
        self.storage_worker.join(timeout=2)
        logger.info("runtime stopped")
