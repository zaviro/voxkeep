"""Logging bootstrap helpers."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure process-wide logging format and level.

    Args:
        level: Desired logging level string.

    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s/%(threadName)s] %(message)s",
    )
