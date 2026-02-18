from __future__ import annotations

import logging
import signal
import threading

logger = logging.getLogger(__name__)


def install_signal_handlers(stop_event: threading.Event) -> None:
    def _handler(signum: int, _frame: object) -> None:
        logger.info("received signal=%s, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
