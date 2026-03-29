"""Public entrypoints for the injection module."""

from __future__ import annotations

import queue
import threading
from typing import Protocol

from asr_ol.modules.injection.application.execute_capture import to_capture_command, to_result
from asr_ol.modules.injection.contracts import InjectionResult
from asr_ol.modules.injection.infrastructure.factory import build_injector
from asr_ol.modules.injection.infrastructure.injector_worker import InjectorWorker
from asr_ol.shared.config import AppConfig
from asr_ol.shared.types import CaptureCompleted
from asr_ol.core.events import CaptureCommand


class InjectionModule(Protocol):
    """Public API exposed by the injection module."""

    def start(self) -> None:
        """Start module resources."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop module resources."""
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        """Join module worker resources."""
        raise NotImplementedError

    def is_alive(self) -> bool:
        """Return whether module worker resources are alive."""
        raise NotImplementedError

    def execute_capture(self, event: CaptureCompleted) -> InjectionResult:
        """Execute the configured output action for a capture event."""
        raise NotImplementedError


class WorkerInjectionModule:
    """Public injection module backed by the legacy worker implementation."""

    def __init__(
        self,
        in_queue: queue.Queue[CaptureCommand],
        stop_event: threading.Event,
        cfg: AppConfig,
    ) -> None:
        """Create an injection module backed by the worker implementation."""
        self._stop_event = stop_event
        self._worker = InjectorWorker(
            in_queue=in_queue,
            stop_event=stop_event,
            injector=build_injector(cfg),
            openclaw_command=cfg.openclaw_command,
            openclaw_timeout_s=cfg.openclaw_timeout_s,
        )

    def start(self) -> None:
        """Start the underlying injection worker."""
        self._worker.start()

    def stop(self) -> None:
        """Expose a symmetric lifecycle hook for the runtime module."""
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        """Join the underlying injection worker."""
        self._worker.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Report whether the underlying worker thread is alive."""
        return self._worker.is_alive()

    def execute_capture(self, event: CaptureCompleted) -> InjectionResult:
        """Execute one capture event through the configured output action."""
        ok = self._worker._execute_action(to_capture_command(event))
        return to_result(event.action, ok)


def build_injection_module(
    *,
    in_queue: queue.Queue[CaptureCommand],
    stop_event: threading.Event,
    cfg: AppConfig,
) -> InjectionModule:
    """Build the injection module public entrypoint."""
    return WorkerInjectionModule(in_queue=in_queue, stop_event=stop_event, cfg=cfg)


__all__ = ["InjectionModule", "WorkerInjectionModule", "build_injection_module"]
