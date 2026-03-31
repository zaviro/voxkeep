"""Runtime status collection helpers for diagnostics and future APIs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Protocol

from voxkeep.modules.runtime.contracts import RuntimeStatus


class QueueLike(Protocol):
    """Protocol for queue-like objects exposing `qsize`."""

    def qsize(self) -> int:
        """Return current queue size."""
        raise NotImplementedError


class EventLike(Protocol):
    """Protocol for event-like objects exposing `is_set`."""

    def is_set(self) -> bool:
        """Report whether the event is set."""
        raise NotImplementedError


class RuntimeLike(Protocol):
    """Protocol describing runtime attributes used by status collector."""

    stop_event: EventLike


def _queue_size(runtime: RuntimeLike, attr_name: str) -> int:
    q = getattr(runtime, attr_name, None)
    if q is None:
        return 0

    qsize = getattr(q, "qsize", None)
    if qsize is None:
        return 0

    try:
        return int(qsize())
    except Exception:
        return 0


def collect_runtime_status(runtime: RuntimeLike) -> RuntimeStatus:
    """Collect queue sizes and running state from runtime object.

    Args:
        runtime: Runtime instance exposing standard queue and stop_event attributes.

    Returns:
        Collected runtime status dataclass.

    """
    queue_names = [
        "raw_queue",
        "wake_audio_queue",
        "vad_audio_queue",
        "asr_audio_queue",
        "wake_event_queue",
        "vad_event_queue",
        "asr_event_bus",
        "capture_cmd_queue",
        "storage_queue",
    ]
    queue_sizes = {name: _queue_size(runtime, name) for name in queue_names}

    stop_event = getattr(runtime, "stop_event", None)
    running = True
    if stop_event is not None:
        try:
            running = not bool(stop_event.is_set())
        except Exception:
            running = True

    return RuntimeStatus(
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        running=running,
        queue_sizes=queue_sizes,
    )


def collect_runtime_status_dict(runtime: RuntimeLike) -> dict[str, Any]:
    """Collect runtime status and return plain dictionary representation."""
    return asdict(collect_runtime_status(runtime))
