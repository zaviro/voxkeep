"""Stable shared value objects used by module public APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(slots=True, frozen=True)
class AudioFrame:
    """Public audio frame submitted to the transcription module."""

    frame_id: int
    data_int16: bytes
    pcm_f32: np.ndarray
    sample_rate: int
    ts_start: float
    ts_end: float


@dataclass(slots=True, frozen=True)
class WakeDetected:
    """Public wake event accepted by the capture module."""

    ts: float
    score: float
    keyword: str


@dataclass(slots=True, frozen=True)
class SpeechBoundaryDetected:
    """Public speech boundary event accepted by the capture module."""

    ts: float
    event_type: Literal["speech_start", "speech_end"]
    score: float


@dataclass(slots=True, frozen=True)
class TranscriptFinalized:
    """Shared transcript event exchanged across module boundaries."""

    segment_id: str
    text: str
    start_ts: float
    end_ts: float
    is_final: bool = True


@dataclass(slots=True, frozen=True)
class CaptureCompleted:
    """Shared capture result exchanged across module boundaries."""

    session_id: int
    keyword: str
    action: str
    text: str
    start_ts: float
    end_ts: float
