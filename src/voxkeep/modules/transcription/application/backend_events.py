"""Backend-neutral transcript events produced by transcription engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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
