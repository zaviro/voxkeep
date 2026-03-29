"""Stage-two storage worker wrapper around the legacy SQLite implementation."""

from asr_ol.infra.storage.storage_worker import StorageWorker as SqliteStorageWorker

__all__ = ["SqliteStorageWorker"]
