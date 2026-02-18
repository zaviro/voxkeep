from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import queue
import sqlite3
import threading

from asr_ol.core.events import StorageRecord

logger = logging.getLogger(__name__)


class StorageWorker:
    def __init__(
        self,
        in_queue: queue.Queue[StorageRecord],
        stop_event: threading.Event,
        sqlite_path: str,
        jsonl_debug_path: str | None = None,
    ) -> None:
        self._in_queue = in_queue
        self._stop_event = stop_event
        self._sqlite_path = Path(sqlite_path)
        self._jsonl_debug_path = Path(jsonl_debug_path) if jsonl_debug_path else None
        self._thread: threading.Thread | None = None
        self._count = 0

    @property
    def write_count(self) -> int:
        return self._count

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="storage_worker", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._sqlite_path)
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

        jsonl_file = None
        if self._jsonl_debug_path is not None:
            self._jsonl_debug_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_file = self._jsonl_debug_path.open("a", encoding="utf-8")

        logger.info("storage worker started sqlite=%s", self._sqlite_path)
        try:
            while not self._stop_event.is_set() or not self._in_queue.empty():
                try:
                    record = self._in_queue.get(timeout=0.1)
                except queue.Empty:
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
                conn.commit()
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
        finally:
            if jsonl_file is not None:
                jsonl_file.close()
            conn.close()
            logger.info("storage worker stopped writes=%s", self._count)
