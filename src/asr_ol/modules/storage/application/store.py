"""Public event to storage-write conversion helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from asr_ol.modules.storage.contracts import StorageWrite
from asr_ol.shared.types import CaptureCompleted, TranscriptFinalized


def build_transcript_write(event: TranscriptFinalized) -> StorageWrite:
    """Convert one transcript event into a storage write request."""
    return StorageWrite(
        source="stream",
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        is_final=event.is_final,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        meta_json=None,
    )


def build_capture_write(event: CaptureCompleted) -> StorageWrite:
    """Convert one capture event into a storage write request."""
    return StorageWrite(
        source="capture",
        text=event.text,
        start_ts=event.start_ts,
        end_ts=event.end_ts,
        is_final=True,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        meta_json=None,
    )
