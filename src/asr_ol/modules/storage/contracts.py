"""Public contracts for the storage module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class StorageWrite:
    """Stable write request accepted by the storage module."""

    source: str
    text: str
    start_ts: float
    end_ts: float
    is_final: bool
    created_at: str
    meta_json: str | None = None
