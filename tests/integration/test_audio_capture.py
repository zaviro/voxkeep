from __future__ import annotations

from dataclasses import replace
import queue

import numpy as np

from voxkeep.shared.config import AppConfig
from voxkeep.modules.runtime.infrastructure.audio_capture import SoundDeviceAudioSource


def test_callback_only_enqueues_audio_chunk(app_config: AppConfig):
    out = queue.Queue(maxsize=2)
    cfg = replace(app_config, max_queue_size=2)
    src = SoundDeviceAudioSource(out_queue=out, cfg=cfg)

    frame = np.zeros((320, 1), dtype=np.int16)
    src._on_audio(frame, 320, None, None)

    item = out.get_nowait()
    assert item.frames == 320
    assert isinstance(item.data, bytes)


def test_callback_drops_when_queue_full(app_config: AppConfig):
    out = queue.Queue(maxsize=1)
    cfg = replace(app_config, max_queue_size=1)
    src = SoundDeviceAudioSource(out_queue=out, cfg=cfg)

    frame = np.zeros((320, 1), dtype=np.int16)
    src._on_audio(frame, 320, None, None)
    src._on_audio(frame, 320, None, None)

    assert src.dropped_chunks == 1
