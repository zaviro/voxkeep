"""Signal handling utilities for graceful runtime shutdown."""

from __future__ import annotations

import logging
import signal
import threading

logger = logging.getLogger(__name__)


def install_signal_handlers(stop_event: threading.Event) -> None:
    """Install SIGINT/SIGTERM handlers that set the stop event.

    Args:
        stop_event: Runtime stop signal shared by workers.

    """

    def _handler(signum: int, _frame: object) -> None:
        logger.info("received signal=%s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
