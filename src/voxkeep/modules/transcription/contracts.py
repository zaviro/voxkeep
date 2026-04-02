"""Public contracts for the transcription module."""

from __future__ import annotations

import queue
from typing import Protocol

from voxkeep.shared.events import ProcessedFrame
from voxkeep.shared.types import TranscriptFinalized


class TranscriptionEngine(Protocol):
    """Structural contract for transcription backends."""

    @property
    def final_queue(self) -> queue.Queue[TranscriptionBackendEvent]:
        """Queue that receives backend transcript events."""
        raise NotImplementedError

    def start(self) -> None:
        """Start engine resources."""
        raise NotImplementedError

    def submit_frame(self, frame: ProcessedFrame) -> None:
        """Submit one processed audio frame."""
        raise NotImplementedError

    def close(self) -> None:
        """Stop engine resources."""
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        """Join engine resources."""
        raise NotImplementedError


class TranscriptionBackendEvent(Protocol):
    """Structural shape for backend transcript events before worker normalization."""

    segment_id: str
    text: str
    start_ts: float
    end_ts: float
    is_final: bool


__all__ = ["TranscriptFinalized", "TranscriptionBackendEvent", "TranscriptionEngine"]
