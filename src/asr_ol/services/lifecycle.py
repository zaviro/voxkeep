from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Worker(Protocol):
    def start(self) -> None:
        raise NotImplementedError

    def join(self, timeout: float | None = None) -> None:
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class WorkerHandle:
    name: str
    worker: Worker
    join_timeout_s: float
