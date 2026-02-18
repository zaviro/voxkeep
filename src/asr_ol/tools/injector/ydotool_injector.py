from __future__ import annotations

import logging
import subprocess

from asr_ol.tools.injector.base import Injector

logger = logging.getLogger(__name__)


class YdotoolInjector(Injector):
    def __init__(self, auto_enter: bool = False):
        self._auto_enter = auto_enter

    def inject(self, text: str) -> bool:
        if not text.strip():
            return False

        try:
            subprocess.run(
                ["ydotool", "type", text],
                check=True,
                capture_output=True,
                text=True,
            )
            if self._auto_enter:
                subprocess.run(
                    ["ydotool", "key", "28:1", "28:0"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            return True
        except Exception as exc:
            logger.error(
                "Wayland injection failed: %s. Hint: ensure ydotoold is running and /dev/uinput permission is configured.",
                exc,
            )
            logger.info("fallback_text=%s", text)
            return False
