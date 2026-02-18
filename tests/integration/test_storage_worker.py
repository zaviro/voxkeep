from datetime import datetime, timezone
import queue
import sqlite3
import threading

from asr_ol.core.events import StorageRecord
from asr_ol.infra.storage.storage_worker import StorageWorker


def test_storage_worker_persists_records(tmp_path):
    q: queue.Queue[StorageRecord] = queue.Queue()
    stop = threading.Event()
    db_path = tmp_path / "asr.db"

    worker = StorageWorker(q, stop, sqlite_path=str(db_path))
    worker.start()

    q.put(
        StorageRecord(
            source="stream",
            text="hello",
            start_ts=1.0,
            end_ts=1.2,
            is_final=True,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
    )
    q.put(
        StorageRecord(
            source="capture",
            text="world",
            start_ts=2.0,
            end_ts=2.2,
            is_final=True,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
    )

    __import__("time").sleep(0.2)
    stop.set()
    worker.join(timeout=2)

    conn = sqlite3.connect(db_path)
    cnt = conn.execute("select count(*) from asr_segments").fetchone()[0]
    conn.close()

    assert cnt == 2
