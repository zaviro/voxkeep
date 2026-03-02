from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any, Mapping, Protocol, Sequence

import numpy as np
from asr_ol.core.config import WakeRuleConfig
from asr_ol.core.events import ProcessedFrame, WakeEvent
from asr_ol.core.queue_utils import put_nowait_or_drop

logger = logging.getLogger(__name__)


_PCM_I16_SCALE = 32768.0
_FRAME_GET_TIMEOUT_S = 0.1


class WakeScorer(Protocol):
    def score(self, frame: ProcessedFrame) -> dict[str, float]:
        raise NotImplementedError


class NullWakeScorer:
    def score(self, frame: ProcessedFrame) -> dict[str, float]:
        _ = frame
        return {}


class OpenWakeWordScorer:
    """Best-effort adapter for openWakeWord streaming score extraction."""

    def __init__(self, model: Any, model_names: Sequence[str]):
        self._model = model
        self._model_names = tuple(model_names)

    @classmethod
    def try_create(cls, model_names: Sequence[str] | None = None) -> WakeScorer:
        try:
            from openwakeword.model import Model
        except Exception as exc:
            logger.warning("openwakeword unavailable; fallback to null scorer: %s", exc)
            return NullWakeScorer()

        selected_models = tuple(
            (str(name).strip() for name in (model_names or []) if str(name).strip())
        )
        if not selected_models:
            fallback = os.environ.get("ASR_OL_WAKE_MODEL", "alexa").strip() or "alexa"
            selected_models = (fallback,)
        try:
            model = Model(wakeword_models=list(selected_models), inference_framework="onnx")
        except Exception as exc:
            logger.warning(
                "openwakeword onnx init failed; fallback to null scorer: %s. "
                "Hint: run `make setup-ai-models`.",
                exc,
            )
            return NullWakeScorer()

        logger.info("openwakeword scorer initialized framework=onnx models=%s", selected_models)
        return cls(model, model_names=selected_models)

    def score(self, frame: ProcessedFrame) -> dict[str, float]:
        pcm_i16 = np.clip(frame.pcm_f32 * _PCM_I16_SCALE, -32768, 32767).astype(np.int16)
        try:
            raw = self._model.predict(pcm_i16)
        except Exception as exc:
            logger.debug("openwakeword predict error: %s", exc)
            return {}

        return _extract_keyword_scores(raw, self._model_names)


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


def _extract_keyword_scores(raw: Any, model_names: Sequence[str]) -> dict[str, float]:
    names = [name for name in model_names if name]
    if not names:
        return {}

    if isinstance(raw, dict):
        return {name: _extract_max_score(raw.get(name, 0.0)) for name in names}

    score = _extract_max_score(raw)
    if len(names) == 1:
        return {names[0]: score}
    return {name: 0.0 for name in names}


class OpenWakeWordWorker:
    def __init__(
        self,
        in_queue: queue.Queue[ProcessedFrame],
        out_queue: queue.Queue[WakeEvent],
        stop_event: threading.Event,
        rules: Sequence[WakeRuleConfig | Mapping[str, Any]],
        scorer: WakeScorer | None = None,
    ) -> None:
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._stop_event = stop_event
        self._rules = _normalize_rules(rules)
        if scorer is not None:
            self._scorer = scorer
        elif self._rules:
            self._scorer = OpenWakeWordScorer.try_create(
                model_names=[rule.keyword for rule in self._rules]
            )
        else:
            logger.warning("wake worker has no enabled rules; detection is disabled")
            self._scorer = NullWakeScorer()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="wake_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        logger.info("wake worker started")
        while not self._stop_event.is_set() or not self._in_queue.empty():
            try:
                frame = self._in_queue.get(timeout=_FRAME_GET_TIMEOUT_S)
            except queue.Empty:
                continue

            event = self._detect(frame)
            if event is not None:
                if put_nowait_or_drop(
                    self._out_queue, event, logger=logger, warning="wake queue full; dropping event"
                ):
                    logger.info("wake detected score=%.3f keyword=%s", event.score, event.keyword)

        logger.info("wake worker stopped")

    def _detect(self, frame: ProcessedFrame) -> WakeEvent | None:
        scores = self._scorer.score(frame)
        matched: list[tuple[float, WakeRuleConfig]] = []
        for rule in self._rules:
            score = float(scores.get(rule.keyword, 0.0))
            if score >= rule.threshold:
                matched.append((score, rule))
        if not matched:
            return None
        score, rule = max(matched, key=lambda item: item[0])
        return WakeEvent(ts=frame.ts_end, score=score, keyword=rule.keyword)


def _normalize_rules(
    rules: Sequence[WakeRuleConfig | Mapping[str, Any]],
) -> tuple[WakeRuleConfig, ...]:
    parsed: list[WakeRuleConfig] = []
    for rule in rules:
        if isinstance(rule, WakeRuleConfig):
            if rule.enabled:
                parsed.append(rule)
            continue
        keyword = str(rule.get("keyword", "")).strip()
        if not keyword:
            continue
        enabled = bool(rule.get("enabled", True))
        if not enabled:
            continue
        parsed.append(
            WakeRuleConfig(
                keyword=keyword,
                enabled=True,
                threshold=float(rule.get("threshold", 0.5)),
                action=str(rule.get("action", "inject_text")).strip() or "inject_text",
            )
        )
    return tuple(parsed)
