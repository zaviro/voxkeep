from datetime import datetime, timezone
import queue
import sqlite3
import threading
import time

from voxkeep.shared.events import StorageRecord
from voxkeep.modules.storage.infrastructure.sqlite_storage_worker import (
    SqliteStorageWorker as StorageWorker,
)


def _record(source: str, text: str, start_ts: float, end_ts: float) -> StorageRecord:
    return StorageRecord(
        source=source,
        text=text,
        start_ts=start_ts,
        end_ts=end_ts,
        is_final=True,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )


def _count_rows(db_path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("select count(*) from asr_segments").fetchone()[0]
    finally:
        conn.close()


def test_storage_worker_persists_records_on_stop_flush(tmp_path):
    q: queue.Queue[StorageRecord] = queue.Queue()
    stop = threading.Event()
    db_path = tmp_path / "asr.db"

    worker = StorageWorker(
        q,
        stop,
        sqlite_path=str(db_path),
        commit_batch_size=100,
        commit_flush_interval_s=60.0,
    )
    worker.start()

    q.put(_record("stream", "hello", 1.0, 1.2))
    q.put(_record("capture", "world", 2.0, 2.2))

    stop.set()
    worker.join(timeout=2)

    assert _count_rows(db_path) == 2


def test_storage_worker_flushes_on_batch_size_without_stop(tmp_path):
    q: queue.Queue[StorageRecord] = queue.Queue()
    stop = threading.Event()
    db_path = tmp_path / "asr.db"

    worker = StorageWorker(
        q,
        stop,
        sqlite_path=str(db_path),
        commit_batch_size=2,
        commit_flush_interval_s=60.0,
    )
    worker.start()

    q.put(_record("stream", "a", 1.0, 1.1))
    q.put(_record("stream", "b", 1.1, 1.2))

    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            if _count_rows(db_path) == 2:
                break
        except sqlite3.OperationalError:
            pass
        time.sleep(0.02)

    stop.set()
    worker.join(timeout=2)

    assert _count_rows(db_path) == 2
