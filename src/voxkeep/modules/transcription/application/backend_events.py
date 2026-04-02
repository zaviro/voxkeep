"""Backend-neutral transcript events produced by transcription engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from voxkeep.modules.transcription.contracts import TranscriptionFinalEvent
from voxkeep.shared.events import AsrFinalEvent


@dataclass(slots=True)
class BackendTranscriptEvent:
    """Normalized transcript event emitted by a transcription backend."""

    segment_id: str
    text: str
    start_ts: float
    end_ts: float
    event_type: Literal["partial", "final"]

    @property
    def is_final(self) -> bool:
        """Return whether the backend event represents a final transcript."""
        return self.event_type == "final"


def to_asr_final_event(event: TranscriptionFinalEvent) -> AsrFinalEvent:
    """Convert a backend transcript event into the public ASR event type."""
    return AsrFinalEvent(
        segment_id=event.segment_id,
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        is_final=event.is_final,
    )
