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
    """Try to enqueue an item without blocking, and drop it on overflow.

    Args:
        q: Target queue.
        item: Item to enqueue.
        logger: Optional logger used when queue is full.
        warning: Optional warning message template.
        on_drop: Optional callback executed when item is dropped.

    Returns:
        True if the item was enqueued; otherwise False.

    """
    try:
        q.put_nowait(item)
        return True
    except queue.Full:
        if on_drop is not None:
            on_drop()
        if logger is not None and warning:
            logger.warning(warning)
        return False
