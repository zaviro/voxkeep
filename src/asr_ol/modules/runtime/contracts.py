"""Public contracts for the runtime module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RuntimeStatus:
    """Stable runtime status summary exposed by the runtime module."""

    running: bool
    queue_sizes: dict[str, int]
    created_at: str
