"""Public entrypoints for the storage module."""

from __future__ import annotations

import queue
import threading
from typing import Protocol

from asr_ol.modules.storage.application.store import build_capture_write, build_transcript_write
from asr_ol.modules.storage.contracts import StorageWrite
from asr_ol.modules.storage.infrastructure.sqlite_storage_worker import SqliteStorageWorker
from asr_ol.shared.config import AppConfig
from asr_ol.shared.types import CaptureCompleted, TranscriptFinalized
from asr_ol.shared.events import StorageRecord


class StorageModule(Protocol):
    """Public API exposed by the storage module."""

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

    def store_transcript(self, event: TranscriptFinalized) -> StorageWrite:
        """Convert one transcript event into a storage write request."""
        raise NotImplementedError

    def store_capture(self, event: CaptureCompleted) -> StorageWrite:
        """Convert one capture event into a storage write request."""
        raise NotImplementedError


class SqliteStorageModule:
    """Public storage module backed by the legacy SQLite worker."""

    def __init__(
        self,
        in_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        cfg: AppConfig,
    ) -> None:
        """Create a storage module backed by the SQLite worker."""
        self._in_queue = in_queue
        self._stop_event = stop_event
        self._worker = SqliteStorageWorker(
            in_queue=in_queue,
            stop_event=stop_event,
            sqlite_path=cfg.sqlite_path,
            jsonl_debug_path=cfg.jsonl_debug_path,
        )

    def start(self) -> None:
        """Start the underlying storage worker."""
        self._worker.start()

    def stop(self) -> None:
        """Expose a symmetric lifecycle hook for the runtime module."""
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        """Join the underlying storage worker."""
        self._worker.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Report whether the underlying worker thread is alive."""
        return self._worker.is_alive()

    def store_transcript(self, event: TranscriptFinalized) -> StorageWrite:
        """Convert a transcript event into a storage write request."""
        return build_transcript_write(event)

    def store_capture(self, event: CaptureCompleted) -> StorageWrite:
        """Convert a capture event into a storage write request."""
        return build_capture_write(event)


def build_storage_module(
    *,
    in_queue: queue.Queue[StorageRecord],
    stop_event: threading.Event,
    cfg: AppConfig,
) -> StorageModule:
    """Build the storage module public entrypoint."""
    return SqliteStorageModule(in_queue=in_queue, stop_event=stop_event, cfg=cfg)


__all__ = ["StorageModule", "SqliteStorageModule", "build_storage_module"]
