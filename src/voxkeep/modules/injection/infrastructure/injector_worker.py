"""Worker that executes post-capture output actions."""

from __future__ import annotations

import logging
import queue
import subprocess
import threading

from voxkeep.shared.events import CaptureCommand
from voxkeep.modules.injection.infrastructure.base import Injector

logger = logging.getLogger(__name__)


_QUEUE_GET_TIMEOUT_S = 0.1


class InjectorWorker:
    """Consume capture commands and trigger configured actions."""

    def __init__(
        self,
        in_queue: queue.Queue[CaptureCommand],
        stop_event: threading.Event,
        injector: Injector,
        openclaw_command: tuple[str, ...],
        openclaw_timeout_s: float,
    ) -> None:
        """Initialize action worker dependencies."""
        self._in_queue = in_queue
        self._stop_event = stop_event
        self._injector = injector
        self._openclaw_command = tuple(openclaw_command)
        self._openclaw_timeout_s = openclaw_timeout_s
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background action execution thread."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="injector_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        """Join the action worker thread."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Return whether the action worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        logger.info("injector worker started")
        while not self._stop_event.is_set() or not self._in_queue.empty():
            try:
                cmd = self._in_queue.get(timeout=_QUEUE_GET_TIMEOUT_S)
            except queue.Empty:
                continue

            ok = self._execute_action(cmd)
            if ok:
                logger.info(
                    "action success session_id=%s keyword=%s action=%s text=%s",
                    cmd.session_id,
                    cmd.keyword,
                    cmd.action,
                    cmd.text,
                )
            else:
                logger.warning(
                    "action failed session_id=%s keyword=%s action=%s text=%s",
                    cmd.session_id,
                    cmd.keyword,
                    cmd.action,
                    cmd.text,
                )

        logger.info("injector worker stopped")

    def _execute_action(self, cmd: CaptureCommand) -> bool:
        if cmd.action == "inject_text":
            return self._injector.inject(cmd.text)
        if cmd.action == "openclaw_agent":
            return self._run_openclaw_agent(cmd.text)
        logger.warning("unknown capture action=%s; skip session_id=%s", cmd.action, cmd.session_id)
        return False

    def _run_openclaw_agent(self, text: str) -> bool:
        argv: list[str] = []
        has_placeholder = False
        for part in self._openclaw_command:
            if "{text}" in part:
                has_placeholder = True
                argv.append(part.replace("{text}", text))
            else:
                argv.append(part)
        if not has_placeholder:
            argv.append(text)

        try:
            subprocess.run(
                argv,
                check=True,
                timeout=self._openclaw_timeout_s,
            )
        except FileNotFoundError as exc:
            logger.warning("openclaw command not found: %s", exc)
            return False
        except subprocess.TimeoutExpired as exc:
            logger.warning("openclaw command timeout: %s", exc)
            return False
        except subprocess.CalledProcessError as exc:
            logger.warning("openclaw command failed: %s", exc)
            return False
        return True
