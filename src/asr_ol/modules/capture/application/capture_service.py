"""Helpers for converting between public and legacy capture types."""

from __future__ import annotations

from asr_ol.core.events import AsrFinalEvent, CaptureCommand, VadEvent, WakeEvent
from asr_ol.shared.types import (
    CaptureCompleted,
    SpeechBoundaryDetected,
    TranscriptFinalized,
    WakeDetected,
)


def to_wake_event(event: WakeDetected) -> WakeEvent:
    """Convert a public wake event into the legacy event type."""
    return WakeEvent(ts=event.ts, score=event.score, keyword=event.keyword)


def to_vad_event(event: SpeechBoundaryDetected) -> VadEvent:
    """Convert a public VAD event into the legacy event type."""
    return VadEvent(ts=event.ts, event_type=event.event_type, score=event.score)


def to_asr_final_event(event: TranscriptFinalized) -> AsrFinalEvent:
    """Convert a public transcript event into the legacy event type."""
    return AsrFinalEvent(
        segment_id=event.segment_id,
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        is_final=event.is_final,
    )


def to_capture_completed(command: CaptureCommand) -> CaptureCompleted:
    """Convert one legacy capture command into the public result type."""
    return CaptureCompleted(
        session_id=command.session_id,
        keyword=command.keyword,
        action=command.action,
        text=command.text,
        start_ts=command.start_ts,
        end_ts=command.end_ts,
    )
