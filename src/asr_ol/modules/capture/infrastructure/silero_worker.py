# ruff: noqa: D100,D101,D102,D107
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Protocol

import numpy as np
from asr_ol.shared.events import ProcessedFrame, VadEvent
from asr_ol.shared.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)


_ENERGY_TO_SCORE_SCALE = 20.0
_FRAME_GET_TIMEOUT_S = 0.1


class VadScorer(Protocol):
    def speech_score(self, frame: ProcessedFrame) -> float:
        raise NotImplementedError


class EnergyVadScorer:
    def speech_score(self, frame: ProcessedFrame) -> float:
        if frame.pcm_f32.size == 0:
            return 0.0
        energy = float((frame.pcm_f32**2).mean())
        return min(1.0, energy * _ENERGY_TO_SCORE_SCALE)


class SileroVadScorer:
    """Best-effort Silero VAD adapter; falls back to energy scorer on runtime errors."""

    def __init__(self, model: Any, torch_module: Any):
        self._model = model
        self._torch = torch_module
        self._fallback = EnergyVadScorer()

    @classmethod
    def try_create(cls) -> VadScorer:
        try:
            import torch
            from silero_vad import load_silero_vad
        except Exception as exc:
            logger.warning("silero-vad unavailable; fallback to energy scorer: %s", exc)
            return EnergyVadScorer()

        try:
            model = load_silero_vad()
        except Exception as exc:
            logger.warning("silero-vad init failed; fallback to energy scorer: %s", exc)
            return EnergyVadScorer()

        logger.info("silero-vad scorer initialized")
        return cls(model, torch)

    def speech_score(self, frame: ProcessedFrame) -> float:
        if frame.pcm_f32.size == 0:
            return 0.0

        try:
            tensor = self._torch.from_numpy(np.asarray(frame.pcm_f32, dtype=np.float32))
            if tensor.dim() == 1:
                tensor = tensor.unsqueeze(0)
            out = self._model(tensor, frame.sample_rate)
            return _extract_score(out)
        except Exception as exc:
            logger.debug("silero-vad predict error: %s", exc)
            return self._fallback.speech_score(frame)


def _extract_score(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, (tuple, list)):
        if not raw:
            return 0.0
        return _extract_score(raw[0])
    if hasattr(raw, "item"):
        try:
            return float(raw.item())
        except Exception:
            return 0.0
    return 0.0


class SileroVadWorker:
    def __init__(
        self,
        in_queue: queue.Queue[ProcessedFrame],
        out_queue: queue.Queue[VadEvent],
        stop_event: threading.Event,
        speech_threshold: float,
        silence_ms: int,
        scorer: VadScorer | None = None,
    ) -> None:
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._stop_event = stop_event
        self._speech_threshold = speech_threshold
        self._silence_ms = silence_ms
        self._scorer = scorer or SileroVadScorer.try_create()
        self._thread: threading.Thread | None = None
        self._speaking = False
        self._silence_acc_ms = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="vad_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        logger.info("vad worker started")
        while not self._stop_event.is_set() or not self._in_queue.empty():
            try:
                frame = self._in_queue.get(timeout=_FRAME_GET_TIMEOUT_S)
            except queue.Empty:
                continue

            score = self._scorer.speech_score(frame)
            frame_ms = (frame.ts_end - frame.ts_start) * 1000.0
            is_speech = score >= self._speech_threshold

            if not self._speaking and is_speech:
                self._speaking = True
                self._silence_acc_ms = 0.0
                self._emit(VadEvent(ts=frame.ts_start, event_type="speech_start", score=score))
                continue

            if self._speaking and is_speech:
                self._silence_acc_ms = 0.0
                continue

            if self._speaking and not is_speech:
                self._silence_acc_ms += frame_ms
                if self._silence_acc_ms >= self._silence_ms:
                    self._speaking = False
                    self._silence_acc_ms = 0.0
                    self._emit(VadEvent(ts=frame.ts_end, event_type="speech_end", score=score))

        logger.info("vad worker stopped")

    def _emit(self, event: VadEvent) -> None:
        if put_nowait_or_drop(
            self._out_queue,
            event,
            logger=logger,
            warning=f"vad queue full; dropping event={event.event_type}",
        ):
            logger.info("vad_event=%s ts=%.3f", event.event_type, event.ts)
