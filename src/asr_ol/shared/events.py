"""Shared event models exchanged by runtime workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(slots=True)
class RawAudioChunk:
    """Raw audio bytes captured from the input source."""

    data: bytes
    frames: int
    sample_rate: int
    channels: int
    ts: float


@dataclass(slots=True)
class ProcessedFrame:
    """Preprocessed frame fanned out to wake/VAD/ASR workers."""

    frame_id: int
    data_int16: bytes
    pcm_f32: np.ndarray
    sample_rate: int
    ts_start: float
    ts_end: float


@dataclass(slots=True)
class WakeEvent:
    """Wake word detection result emitted by wake worker."""

    ts: float
    score: float
    keyword: str


@dataclass(slots=True)
class VadEvent:
    """Voice activity transition emitted by VAD worker."""

    ts: float
    event_type: Literal["speech_start", "speech_end"]
    score: float


@dataclass(slots=True)
class AsrFinalEvent:
    """ASR final transcript segment."""

    segment_id: str
    text: str
    start_ts: float
    end_ts: float
    is_final: bool = True


@dataclass(slots=True)
class CaptureCommand:
    """Final capture output that triggers downstream action."""

    session_id: int
    keyword: str
    action: str
    text: str
    start_ts: float
    end_ts: float


@dataclass(slots=True)
class StorageRecord:
    """Persistable transcript or capture record."""

    source: str
    text: str
    start_ts: float
    end_ts: float
    is_final: bool
    created_at: str
    meta_json: str | None = None
