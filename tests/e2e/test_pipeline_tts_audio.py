from __future__ import annotations

from dataclasses import replace
import math
import queue
import threading

import numpy as np
import pytest

from asr_ol.agents.capture_fsm import CaptureFSM
from asr_ol.agents.capture_worker import CaptureWorker
from asr_ol.agents.transcript_extractor import InMemoryTranscriptExtractor
from asr_ol.core.config import AppConfig
from asr_ol.core.events import (
    AsrFinalEvent,
    ProcessedFrame,
    RawAudioChunk,
    StorageRecord,
    VadEvent,
    WakeEvent,
)
from asr_ol.services.asr_worker import AsrWorker
from asr_ol.services.audio_bus import AudioBus


class FakeStreamingAsrEngine:
    def __init__(self, transcript: str | None):
        self.final_queue: queue.Queue[AsrFinalEvent] = queue.Queue()
        self._transcript = transcript
        self._started = False
        self._closed = False
        self._emitted = False

    def start(self) -> None:
        self._started = True

    def submit_frame(self, frame: ProcessedFrame) -> None:
        if self._emitted or not self._transcript:
            return
        if float(np.max(np.abs(frame.pcm_f32))) < 0.02:
            return
        self._emitted = True
        self.final_queue.put_nowait(
            AsrFinalEvent(
                segment_id="seg-tts",
                text=self._transcript,
                start_ts=frame.ts_start,
                end_ts=frame.ts_end,
                is_final=True,
            )
        )

    def close(self) -> None:
        self._closed = True


def _synthesize_tts_pcm(text: str, sample_rate: int) -> np.ndarray:
    cleaned = text.strip()
    if not cleaned:
        return np.zeros(sample_rate // 4, dtype=np.float32)

    chunks: list[np.ndarray] = []
    char_ms = 90
    gap_ms = 15
    for idx, char in enumerate(cleaned):
        freq = 180.0 + (ord(char) % 40) * 9.0 + (idx % 3) * 7.0
        sample_count = max(1, int(sample_rate * (char_ms / 1000.0)))
        t = np.arange(sample_count, dtype=np.float32) / float(sample_rate)
        wave = 0.22 * np.sin(2.0 * math.pi * freq * t)
        wave += 0.08 * np.sin(2.0 * math.pi * (freq * 2.0) * t)

        fade_len = min(80, sample_count // 4)
        if fade_len > 0:
            ramp = np.linspace(0.0, 1.0, num=fade_len, endpoint=True, dtype=np.float32)
            wave[:fade_len] *= ramp
            wave[-fade_len:] *= ramp[::-1]

        chunks.append(wave.astype(np.float32))
        gap = np.zeros(int(sample_rate * (gap_ms / 1000.0)), dtype=np.float32)
        chunks.append(gap)

    return np.concatenate(chunks, dtype=np.float32)


def _chunk_raw_audio(
    pcm_f32: np.ndarray,
    *,
    sample_rate: int,
    frame_samples: int,
    ts_base: float,
) -> list[RawAudioChunk]:
    pcm_i16 = np.clip(pcm_f32 * 32768.0, -32768, 32767).astype(np.int16)
    chunks: list[RawAudioChunk] = []

    for offset in range(0, len(pcm_i16), frame_samples):
        frame = pcm_i16[offset : offset + frame_samples]
        if frame.size < frame_samples:
            frame = np.pad(frame, (0, frame_samples - frame.size), mode="constant")
        ts = ts_base + (offset / sample_rate)
        chunks.append(
            RawAudioChunk(
                data=frame.tobytes(),
                frames=frame_samples,
                sample_rate=sample_rate,
                channels=1,
                ts=ts,
            )
        )

    return chunks


@pytest.mark.parametrize(
    ("text", "expect_command"),
    [
        ("ni hao tts", True),
        ("   ", False),
    ],
)
def test_tts_audio_stream_end_to_end(text: str, expect_command: bool, app_config: AppConfig):
    cfg = replace(
        app_config, frame_ms=20, pre_roll_ms=120, armed_timeout_ms=3000, max_queue_size=64
    )
    stop_event = threading.Event()

    raw_q: queue.Queue[RawAudioChunk] = queue.Queue(maxsize=cfg.max_queue_size)
    wake_audio_q: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
    vad_audio_q: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)
    asr_audio_q: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=cfg.max_queue_size)

    wake_event_q: queue.Queue[WakeEvent] = queue.Queue(maxsize=cfg.max_queue_size)
    vad_event_q: queue.Queue[VadEvent] = queue.Queue(maxsize=cfg.max_queue_size)
    asr_event_bus: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
    capture_asr_q: queue.Queue[AsrFinalEvent] = queue.Queue(maxsize=cfg.max_queue_size)
    capture_cmd_q = queue.Queue(maxsize=cfg.max_queue_size)
    storage_q: queue.Queue[StorageRecord] = queue.Queue(maxsize=cfg.max_queue_size)

    audio_bus = AudioBus(
        raw_queue=raw_q,
        wake_queue=wake_audio_q,
        vad_queue=vad_audio_q,
        asr_queue=asr_audio_q,
        stop_event=stop_event,
    )

    transcript = text.strip() or None
    engine = FakeStreamingAsrEngine(transcript=transcript)
    asr_worker = AsrWorker(
        in_queue=asr_audio_q,
        final_in_queue=engine.final_queue,
        out_queue=asr_event_bus,
        capture_queue=capture_asr_q,
        storage_queue=storage_q,
        stop_event=stop_event,
        engine=engine,
        store_final_only=True,
    )

    capture_worker = CaptureWorker(
        wake_queue=wake_event_q,
        vad_queue=vad_event_q,
        asr_queue=capture_asr_q,
        out_queue=capture_cmd_q,
        storage_queue=storage_q,
        stop_event=stop_event,
        fsm=CaptureFSM(pre_roll_ms=cfg.pre_roll_ms, armed_timeout_ms=cfg.armed_timeout_ms),
        transcript_extractor=InMemoryTranscriptExtractor(),
        action_by_keyword={"alexa": "inject_text"},
        default_action="inject_text",
    )

    tts_pcm = _synthesize_tts_pcm(text, cfg.sample_rate)
    ts_base = 100.0
    raw_chunks = _chunk_raw_audio(
        tts_pcm,
        sample_rate=cfg.sample_rate,
        frame_samples=cfg.frame_samples,
        ts_base=ts_base,
    )

    wake_event_q.put(WakeEvent(ts=ts_base + 0.02, score=0.95, keyword="alexa"))
    vad_event_q.put(VadEvent(ts=ts_base + 0.03, event_type="speech_start", score=0.9))

    for raw in raw_chunks:
        raw_q.put(raw)
        audio_bus.run_once(timeout=0.01)
        asr_worker._submit_audio_once()
        asr_worker._drain_final_events()
        capture_worker._consume_once()

    vad_event_q.put(
        VadEvent(
            ts=ts_base + (len(raw_chunks) * cfg.frame_ms / 1000.0) + 0.05,
            event_type="speech_end",
            score=0.1,
        )
    )

    for _ in range(8):
        asr_worker._drain_final_events()
        capture_worker._consume_once()
        if not capture_cmd_q.empty():
            break

    if expect_command:
        cmd = capture_cmd_q.get_nowait()
        assert cmd.action == "inject_text"
        assert cmd.keyword == "alexa"
        assert cmd.text == text.strip()
        assert storage_q.qsize() >= 2
        assert asr_event_bus.qsize() == 1
    else:
        assert capture_cmd_q.empty()
        assert storage_q.empty()
        assert asr_event_bus.empty()
