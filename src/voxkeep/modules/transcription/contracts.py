"""Public contracts for the transcription module."""

from __future__ import annotations

import queue
from typing import Protocol

from voxkeep.shared.events import ProcessedFrame
from voxkeep.shared.types import TranscriptFinalized


class TranscriptionEngine(Protocol):
    """Structural contract for transcription backends."""

    @property
    def final_queue(self) -> queue.Queue[TranscriptionFinalEvent]:
        """Queue that receives finalized transcript events."""
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


class TranscriptionFinalEvent(Protocol):
    """Backend-neutral structural shape for finalized transcript events."""

    segment_id: str
    text: str
    start_ts: float
    end_ts: float
    is_final: bool


__all__ = ["TranscriptFinalized", "TranscriptionEngine", "TranscriptionFinalEvent"]
