from __future__ import annotations

import queue
import threading

import pytest

from voxkeep.modules.storage.infrastructure.sqlite_storage_worker import (
    SqliteStorageWorker as StorageWorker,
)


@pytest.mark.parametrize(
    ("kwargs", "match_text"),
    [
        ({"commit_batch_size": 0}, "commit_batch_size"),
        ({"commit_flush_interval_s": 0.0}, "commit_flush_interval_s"),
    ],
)
def test_storage_worker_rejects_invalid_init_args(kwargs: dict[str, object], match_text: str):
    with pytest.raises(ValueError, match=match_text):
        StorageWorker(
            in_queue=queue.Queue(),
            stop_event=threading.Event(),
            sqlite_path=":memory:",
            **kwargs,
        )
