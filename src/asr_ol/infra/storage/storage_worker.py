"""Compatibility wrapper for the SQLite storage worker implementation."""

from asr_ol.modules.storage.infrastructure.sqlite_storage_worker import (
    SqliteStorageWorker as StorageWorker,
)

__all__ = ["StorageWorker"]
