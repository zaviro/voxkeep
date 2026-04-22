"""Lifecycle abstractions for runtime worker management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Worker(Protocol):
    """Define the minimal runtime worker lifecycle contract."""

    def start(self) -> None:
        """Start worker resources and background processing."""
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        """Block until worker exits or timeout is reached."""
        raise NotImplementedError

    def is_alive(self) -> bool:
        """Report whether the worker background task is still running."""
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class WorkerHandle:
    """Bind a worker to a logical name and shutdown timeout."""

    name: str
    worker: Worker
    join_timeout_s: float
