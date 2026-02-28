from __future__ import annotations

from collections import deque
from typing import Protocol

from asr_ol.core.events import AsrFinalEvent


class TranscriptExtractor(Protocol):
    def on_asr_final(self, event: AsrFinalEvent) -> None:
        raise NotImplementedError

    def extract(self, start_ts: float, end_ts: float) -> str:
        raise NotImplementedError


class InMemoryTranscriptExtractor:
    def __init__(self, max_segments: int = 4096):
        self._asr_finals: deque[AsrFinalEvent] = deque(maxlen=max_segments)

    def on_asr_final(self, event: AsrFinalEvent) -> None:
        if event.is_final:
            self._asr_finals.append(event)

    def extract(self, start_ts: float, end_ts: float) -> str:
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
