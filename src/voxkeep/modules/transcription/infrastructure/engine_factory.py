"""Factory for constructing transcription engines."""

from __future__ import annotations

import threading
from typing import Callable

from voxkeep.modules.transcription.contracts import TranscriptionEngine
from voxkeep.modules.transcription.infrastructure.funasr_ws import FunAsrWsEngine
from voxkeep.shared.asr_backends import resolve_backend_definition
from voxkeep.shared.config import AppConfig


def _build_funasr_ws_engine(*, cfg: AppConfig, stop_event: threading.Event) -> TranscriptionEngine:
    return FunAsrWsEngine(cfg=cfg, stop_event=stop_event)


BACKEND_ENGINE_BUILDERS: dict[str, Callable[..., TranscriptionEngine]] = {
    "funasr_ws_external": _build_funasr_ws_engine,
    "funasr_ws_managed": _build_funasr_ws_engine,
}


def build_asr_engine(*, cfg: AppConfig, stop_event: threading.Event) -> TranscriptionEngine:
    """Build the configured ASR engine."""
    backend_id = resolve_backend_definition(cfg.asr_backend).backend_id
    try:
        builder = BACKEND_ENGINE_BUILDERS[backend_id]
    except KeyError as exc:
        raise ValueError(f"unsupported asr backend: {cfg.asr_backend}") from exc
    return builder(cfg=cfg, stop_event=stop_event)
