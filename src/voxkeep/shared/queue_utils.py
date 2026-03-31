"""Queue helper utilities shared across worker implementations."""

from __future__ import annotations

import logging
import queue
from typing import Callable, TypeVar

T = TypeVar("T")


def put_nowait_or_drop(
    q: queue.Queue[T],
    item: T,
    *,
    logger: logging.Logger | None = None,
    warning: str | None = None,
    on_drop: Callable[[], None] | None = None,
) -> bool:
    """Try to enqueue an item without blocking, and drop it on overflow."""
    try:
        q.put_nowait(item)
        return True
    except queue.Full:
        if on_drop is not None:
            on_drop()
        if logger is not None and warning:
            logger.warning(warning)
        return False


__all__ = ["put_nowait_or_drop"]
