# ruff: noqa: D100,D107,D102
from __future__ import annotations

import numpy as np

from asr_ol.shared.events import ProcessedFrame, RawAudioChunk


class Preprocessor:
    """Single-pass preprocessor. Output can be shared by wake/vad/asr."""

    def __init__(self) -> None:
        self._frame_id = 0

    def process(self, chunk: RawAudioChunk) -> ProcessedFrame:
        pcm = np.frombuffer(chunk.data, dtype=np.int16)
        if chunk.channels > 1:
            pcm = pcm.reshape(-1, chunk.channels).mean(axis=1).astype(np.int16)

        pcm_f32 = pcm.astype(np.float32) / 32768.0
        ts_end = chunk.ts
        ts_start = ts_end - (chunk.frames / float(chunk.sample_rate))
        self._frame_id += 1

        return ProcessedFrame(
            frame_id=self._frame_id,
            data_int16=pcm.tobytes(),
            pcm_f32=pcm_f32,
            sample_rate=chunk.sample_rate,
            ts_start=ts_start,
            ts_end=ts_end,
        )
