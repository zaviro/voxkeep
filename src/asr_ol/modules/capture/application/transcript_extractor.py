"""Transcript extraction helpers for the capture module."""

from __future__ import annotations

from collections import deque
from typing import Protocol

from asr_ol.core.events import AsrFinalEvent


class TranscriptExtractor(Protocol):
    """Protocol for transcript accumulation and time-window extraction."""

    def on_asr_final(self, event: AsrFinalEvent) -> None:
        """Consume one ASR final event."""
        raise NotImplementedError

    def extract(self, start_ts: float, end_ts: float) -> str:
        """Extract transcript text overlapping the requested time range."""
        raise NotImplementedError


class InMemoryTranscriptExtractor:
    """Bounded in-memory transcript cache."""

    def __init__(self, max_segments: int = 4096):
        """Create transcript buffer with bounded history."""
        self._asr_finals: deque[AsrFinalEvent] = deque(maxlen=max_segments)

    def on_asr_final(self, event: AsrFinalEvent) -> None:
        """Store finalized transcript segments."""
        if event.is_final:
            self._asr_finals.append(event)

    def extract(self, start_ts: float, end_ts: float) -> str:
        """Return concatenated text for overlapping finalized segments."""
        texts: list[str] = []
        for seg in self._asr_finals:
            if seg.end_ts < start_ts:
                continue
            if seg.start_ts > end_ts:
                continue
            cleaned = seg.text.strip()
            if cleaned:
                texts.append(cleaned)
        return " ".join(texts).strip()
