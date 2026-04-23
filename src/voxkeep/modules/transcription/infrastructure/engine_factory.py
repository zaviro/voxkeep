"""Factory for constructing transcription engines."""

from __future__ import annotations

import threading
from typing import Callable

from voxkeep.modules.transcription.contracts import TranscriptionEngine
from voxkeep.modules.transcription.infrastructure.qwen_vllm import QwenVllmEngine
from voxkeep.shared.asr_backends import resolve_backend_definition
from voxkeep.shared.config import AsrConfig


def _build_qwen_vllm_engine(*, cfg: AsrConfig, stop_event: threading.Event) -> TranscriptionEngine:
    return QwenVllmEngine(cfg=cfg, stop_event=stop_event)


BACKEND_ENGINE_BUILDERS: dict[str, Callable[..., TranscriptionEngine]] = {
    "qwen_vllm": _build_qwen_vllm_engine,
}


def build_asr_engine(*, cfg: AsrConfig, stop_event: threading.Event) -> TranscriptionEngine:
    """Build the configured ASR engine."""
    backend_id = resolve_backend_definition(cfg.backend).backend_id
    try:
        builder = BACKEND_ENGINE_BUILDERS[backend_id]
    except KeyError as exc:
        raise ValueError(f"unsupported asr backend: {cfg.backend}") from exc
    return builder(cfg=cfg, stop_event=stop_event)
