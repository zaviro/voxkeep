from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Protocol

import numpy as np
from asr_ol.core.events import ProcessedFrame, WakeEvent

logger = logging.getLogger(__name__)


class WakeScorer(Protocol):
    def score(self, frame: ProcessedFrame) -> float:
        raise NotImplementedError


class NullWakeScorer:
    def score(self, frame: ProcessedFrame) -> float:
        _ = frame
        return 0.0


class OpenWakeWordScorer:
    """Best-effort adapter for openWakeWord streaming score extraction."""

    def __init__(self, model: Any):
        self._model = model

    @classmethod
    def try_create(cls) -> WakeScorer:
        try:
            from openwakeword.model import Model
        except Exception as exc:
            logger.warning("openwakeword unavailable; fallback to null scorer: %s", exc)
            return NullWakeScorer()

        try:
            model = Model()
        except Exception as exc:
            logger.warning("openwakeword init failed; fallback to null scorer: %s", exc)
            return NullWakeScorer()

        logger.info("openwakeword scorer initialized")
        return cls(model)

    def score(self, frame: ProcessedFrame) -> float:
        pcm_i16 = np.clip(frame.pcm_f32 * 32768.0, -32768, 32767).astype(np.int16)
        try:
            raw = self._model.predict(pcm_i16)
        except Exception as exc:
            logger.debug("openwakeword predict error: %s", exc)
            return 0.0

        return _extract_max_score(raw)


def _extract_max_score(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        scores = [_extract_max_score(v) for v in raw.values()]
        return max(scores) if scores else 0.0
    if isinstance(raw, (list, tuple)):
        scores = [_extract_max_score(v) for v in raw]
        return max(scores) if scores else 0.0
    if hasattr(raw, "item"):
        try:
            return float(raw.item())
        except Exception:
            return 0.0
    return 0.0


class OpenWakeWordWorker:
    def __init__(
        self,
        in_queue: queue.Queue[ProcessedFrame],
        out_queue: queue.Queue[WakeEvent],
        stop_event: threading.Event,
        threshold: float,
        scorer: WakeScorer | None = None,
        keyword: str = "wake",
    ) -> None:
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._stop_event = stop_event
        self._threshold = threshold
        self._scorer = scorer or OpenWakeWordScorer.try_create()
        self._keyword = keyword
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="wake_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        logger.info("wake worker started")
        while not self._stop_event.is_set() or not self._in_queue.empty():
            try:
                frame = self._in_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            score = self._scorer.score(frame)
            if score >= self._threshold:
                event = WakeEvent(ts=frame.ts_end, score=score, keyword=self._keyword)
                try:
                    self._out_queue.put_nowait(event)
                    logger.info("wake detected score=%.3f keyword=%s", score, self._keyword)
                except queue.Full:
                    logger.warning("wake queue full; dropping event")

        logger.info("wake worker stopped")
