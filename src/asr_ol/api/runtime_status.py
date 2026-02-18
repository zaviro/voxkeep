from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


class QueueLike(Protocol):
    def qsize(self) -> int:
        raise NotImplementedError


class EventLike(Protocol):
    def is_set(self) -> bool:
        raise NotImplementedError


class RuntimeLike(Protocol):
    stop_event: EventLike


@dataclass(slots=True)
class RuntimeStatus:
    created_at: str
    running: bool
    queue_sizes: dict[str, int]


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
    return asdict(collect_runtime_status(runtime))
