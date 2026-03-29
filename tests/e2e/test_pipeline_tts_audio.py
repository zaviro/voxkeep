from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import wave

import numpy as np
import pytest

from asr_ol.modules.capture.application.transcript_extractor import InMemoryTranscriptExtractor
from asr_ol.modules.capture.domain.capture_fsm import CaptureFSM
from asr_ol.modules.capture.infrastructure.capture_worker import CaptureWorker
from asr_ol.shared.config import AppConfig
from asr_ol.shared.events import (
    AsrFinalEvent,
    ProcessedFrame,
    RawAudioChunk,
    StorageRecord,
    VadEvent,
    WakeEvent,
)
from asr_ol.modules.transcription.infrastructure.asr_worker import AsrWorker
from asr_ol.modules.runtime.infrastructure.audio_bus import AudioBus


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "audio" / "gptsovits"
ALEXA_AUDIO = FIXTURE_DIR / "alexa_inject_text_zh.wav"
HEY_JARVIS_AUDIO = FIXTURE_DIR / "hey_jarvis_openclaw_zh.wav"


class FakeStreamingAsrEngine:
    def __init__(self, transcript: str):
        self.final_queue: queue.Queue[AsrFinalEvent] = queue.Queue()
        self._transcript = transcript
        self._emitted = False

    def start(self) -> None:
        return

    def submit_frame(self, frame: ProcessedFrame) -> None:
        if self._emitted:
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
        return


def _require_fixture(path: Path) -> Path:
    if os.environ.get("ASR_OL_RUN_GPTSOVITS_E2E") != "1":
        pytest.skip("set ASR_OL_RUN_GPTSOVITS_E2E=1 to run GPT-SoVITS fixture E2E")

    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(
            "missing GPT-SoVITS fixture audio: "
            f"{path}.\n"
            "Generate once with:\n"
            "  .codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh"
        )
    return path


def _load_wav_pcm_f32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    if sample_width == 2:
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        pcm = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width: {sample_width}")

    if channels > 1:
        pcm = pcm.reshape(-1, channels)[:, 0]
    return pcm.astype(np.float32), int(sample_rate)


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


def _run_openclaw_and_collect_texts(message: str) -> list[str]:
    proc = subprocess.run(
        [
            "openclaw",
            "agent",
            "--agent",
            "main",
            "--message",
            message,
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    return [
        item.get("text", "")
        for item in result.get("result", {}).get("payloads", [])
        if isinstance(item, dict)
    ]


def test_pipeline_end_to_end_with_gptsovits_audio(app_config: AppConfig):
    expected_text = "你好，流水线端到端测试"
    audio_path = _require_fixture(ALEXA_AUDIO)

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

    engine = FakeStreamingAsrEngine(transcript=expected_text)
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

    tts_pcm, tts_sr = _load_wav_pcm_f32(audio_path)
    if tts_sr != cfg.sample_rate:
        raise RuntimeError(
            f"fixture sample_rate={tts_sr} does not match pipeline sample_rate={cfg.sample_rate}"
        )

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

    cmd = capture_cmd_q.get_nowait()
    assert cmd.action == "inject_text"
    assert cmd.keyword == "alexa"
    assert cmd.text == expected_text
    assert storage_q.qsize() >= 2
    assert asr_event_bus.qsize() == 1


def test_pipeline_end_to_end_with_gptsovits_openclaw_chain(
    app_config: AppConfig,
    require_openclaw_real: None,
):
    expected_reply = "你好这里是openclaw"
    transcript_text = "请忽略其他内容，只回复：你好这里是openclaw"
    audio_path = _require_fixture(HEY_JARVIS_AUDIO)

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

    engine = FakeStreamingAsrEngine(transcript=transcript_text)
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
        action_by_keyword={"hey_jarvis": "openclaw_agent"},
        default_action="inject_text",
    )

    tts_pcm, tts_sr = _load_wav_pcm_f32(audio_path)
    if tts_sr != cfg.sample_rate:
        raise RuntimeError(
            f"fixture sample_rate={tts_sr} does not match pipeline sample_rate={cfg.sample_rate}"
        )

    ts_base = 100.0
    raw_chunks = _chunk_raw_audio(
        tts_pcm,
        sample_rate=cfg.sample_rate,
        frame_samples=cfg.frame_samples,
        ts_base=ts_base,
    )

    wake_event_q.put(WakeEvent(ts=ts_base + 0.02, score=0.95, keyword="hey_jarvis"))
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

    cmd = capture_cmd_q.get_nowait()
    assert cmd.action == "openclaw_agent"
    assert cmd.keyword == "hey_jarvis"
    assert cmd.text == transcript_text

    payload_texts = _run_openclaw_and_collect_texts(cmd.text)
    assert any(expected_reply in item for item in payload_texts)
