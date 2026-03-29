"""SQLite-backed storage worker for ASR and capture records."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import queue
import sqlite3
import threading
import time

from asr_ol.shared.events import StorageRecord

logger = logging.getLogger(__name__)


_QUEUE_GET_TIMEOUT_S = 0.1


class SqliteStorageWorker:
    """Persist storage records to SQLite and optional JSONL debug stream."""

    def __init__(
        self,
        in_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        sqlite_path: str,
        jsonl_debug_path: str | None = None,
        commit_batch_size: int = 32,
        commit_flush_interval_s: float = 0.5,
    ) -> None:
        """Initialize worker with batching and flush policies."""
        if commit_batch_size < 1:
            raise ValueError("commit_batch_size must be >= 1")
        if commit_flush_interval_s <= 0:
            raise ValueError("commit_flush_interval_s must be > 0")

        self._in_queue = in_queue
        self._stop_event = stop_event
        self._sqlite_path = Path(sqlite_path)
        self._jsonl_debug_path = Path(jsonl_debug_path) if jsonl_debug_path else None
        self._commit_batch_size = int(commit_batch_size)
        self._commit_flush_interval_s = float(commit_flush_interval_s)
        self._thread: threading.Thread | None = None
        self._count = 0

    @property
    def write_count(self) -> int:
        """Return number of records written by this worker."""
        return self._count

    def start(self) -> None:
        """Start background storage thread once."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="storage_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        """Join storage thread."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """Return whether storage thread is currently alive."""
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._sqlite_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asr_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                text TEXT NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL NOT NULL,
                is_final INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                meta_json TEXT
            )
            """
        )
        conn.commit()
        pending_count = 0
        last_commit_at = time.monotonic()

        jsonl_file = None
        if self._jsonl_debug_path is not None:
            self._jsonl_debug_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_file = self._jsonl_debug_path.open("a", encoding="utf-8")

        def flush_pending(force: bool = False) -> None:
            nonlocal pending_count, last_commit_at
            if pending_count == 0:
                return
            now = time.monotonic()
            if (
                force
                or pending_count >= self._commit_batch_size
                or (now - last_commit_at) >= self._commit_flush_interval_s
            ):
                conn.commit()
                pending_count = 0
                last_commit_at = now

        logger.info("storage worker started sqlite=%s", self._sqlite_path)
        try:
            while not self._stop_event.is_set() or not self._in_queue.empty():
                try:
                    record = self._in_queue.get(timeout=_QUEUE_GET_TIMEOUT_S)
                except queue.Empty:
                    flush_pending()
                    continue

                created_at = record.created_at or datetime.now(tz=timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO asr_segments (source, text, start_ts, end_ts, is_final, created_at, meta_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.source,
                        record.text,
                        record.start_ts,
                        record.end_ts,
                        1 if record.is_final else 0,
                        created_at,
                        record.meta_json,
                    ),
                )
                pending_count += 1
                self._count += 1

                if jsonl_file is not None:
                    jsonl_file.write(
                        json.dumps(
                            {
                                "source": record.source,
                                "text": record.text,
                                "start_ts": record.start_ts,
                                "end_ts": record.end_ts,
                                "is_final": record.is_final,
                                "created_at": created_at,
                                "meta_json": record.meta_json,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    jsonl_file.flush()
                flush_pending()
        finally:
            flush_pending(force=True)
            if jsonl_file is not None:
                jsonl_file.close()
            conn.close()
            logger.info("storage worker stopped writes=%s", self._count)
