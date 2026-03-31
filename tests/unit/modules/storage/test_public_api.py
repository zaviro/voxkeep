from __future__ import annotations

import queue
import threading

from voxkeep.modules.storage.contracts import StorageWrite
from voxkeep.modules.storage.public import build_storage_module
from voxkeep.shared.config import AppConfig
from voxkeep.shared.types import CaptureCompleted, TranscriptFinalized


def test_storage_module_converts_public_events_to_storage_writes(app_config: AppConfig) -> None:
    module = build_storage_module(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        cfg=app_config,
    )

    transcript_write = module.store_transcript(
        TranscriptFinalized(
            segment_id="seg-1",
            text="hello",
            start_ts=1.0,
            end_ts=1.2,
        )
    )
    capture_write = module.store_capture(
        CaptureCompleted(
            session_id=1,
            keyword="alexa",
            action="inject_text",
            text="world",
            start_ts=2.0,
            end_ts=2.2,
        )
    )

    assert transcript_write == StorageWrite(
        source="stream",
        text="hello",
        start_ts=1.0,
        end_ts=1.2,
        is_final=True,
        created_at=transcript_write.created_at,
        meta_json=None,
    )
    assert capture_write == StorageWrite(
        source="capture",
        text="world",
        start_ts=2.0,
        end_ts=2.2,
        is_final=True,
        created_at=capture_write.created_at,
        meta_json=None,
    )


def test_storage_module_stop_sets_stop_event(app_config: AppConfig) -> None:
    stop_event = threading.Event()
    module = build_storage_module(
        in_queue=queue.Queue(),
        stop_event=stop_event,
        cfg=app_config,
    )

    module.stop()

    assert stop_event.is_set() is True
