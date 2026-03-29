"""Compatibility wrapper for transcript extraction helpers."""

from asr_ol.modules.capture.application.transcript_extractor import (
    InMemoryTranscriptExtractor,
    TranscriptExtractor,
)

__all__ = ["TranscriptExtractor", "InMemoryTranscriptExtractor"]
