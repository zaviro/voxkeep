"""Helpers for converting between public and legacy transcription types."""

from __future__ import annotations

from voxkeep.shared.events import AsrFinalEvent, ProcessedFrame
from voxkeep.shared.types import AudioFrame, TranscriptFinalized


def to_processed_frame(frame: AudioFrame) -> ProcessedFrame:
    """Convert a public audio frame into the legacy processed frame type."""
    return ProcessedFrame(
        frame_id=frame.frame_id,
        data_int16=frame.data_int16,
        pcm_f32=frame.pcm_f32,
        sample_rate=frame.sample_rate,
        ts_start=frame.ts_start,
        ts_end=frame.ts_end,
    )


def to_transcript_finalized(event: AsrFinalEvent) -> TranscriptFinalized:
    """Convert one legacy ASR event into the public transcript type."""
    return TranscriptFinalized(
        segment_id=event.segment_id,
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        is_final=event.is_final,
    )
