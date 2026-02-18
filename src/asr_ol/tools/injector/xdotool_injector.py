from __future__ import annotations

import logging
import subprocess

from asr_ol.tools.injector.base import Injector

logger = logging.getLogger(__name__)


class XdotoolInjector(Injector):
    def __init__(self, delay_ms: int = 1, auto_enter: bool = False):
        self._delay_ms = delay_ms
        self._auto_enter = auto_enter

    def inject(self, text: str) -> bool:
        if not text.strip():
            return False
        try:
            subprocess.run(
                [
                    "xdotool",
                    "type",
                    "--clearmodifiers",
                    "--delay",
                    str(self._delay_ms),
                    "--",
                    text,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            if self._auto_enter:
                subprocess.run(
                    ["xdotool", "key", "Return"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            return True
        except Exception as exc:
            logger.error("xdotool injection failed: %s", exc)
            return False
