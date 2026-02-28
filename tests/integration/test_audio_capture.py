import queue

import numpy as np

from asr_ol.infra.audio.audio_capture import SoundDeviceAudioSource
from asr_ol.core.config import AppConfig, WakeRuleConfig


def _cfg() -> AppConfig:
    return AppConfig(
        sample_rate=16000,
        channels=1,
        frame_ms=20,
        max_queue_size=2,
        funasr_host="127.0.0.1",
        funasr_port=10096,
        funasr_path="/",
        funasr_use_ssl=False,
        asr_reconnect_initial_s=1.0,
        asr_reconnect_max_s=30.0,
        wake_threshold=0.5,
        wake_rules=(
            WakeRuleConfig(
                keyword="alexa",
                enabled=True,
                threshold=0.5,
                action="inject_text",
            ),
        ),
        vad_speech_threshold=0.5,
        vad_silence_ms=800,
        pre_roll_ms=600,
        armed_timeout_ms=5000,
        sqlite_path=":memory:",
        store_final_only=True,
        jsonl_debug_path=None,
        injector_backend="xdotool",
        injector_auto_enter=False,
        xdotool_delay_ms=1,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
        log_level="INFO",
    )


def test_callback_only_enqueues_audio_chunk():
    out = queue.Queue(maxsize=2)
    src = SoundDeviceAudioSource(out_queue=out, cfg=_cfg())

    frame = np.zeros((320, 1), dtype=np.int16)
    src._on_audio(frame, 320, None, None)

    item = out.get_nowait()
    assert item.frames == 320
    assert isinstance(item.data, bytes)


def test_callback_drops_when_queue_full():
    out = queue.Queue(maxsize=1)
    src = SoundDeviceAudioSource(out_queue=out, cfg=_cfg())

    frame = np.zeros((320, 1), dtype=np.int16)
    src._on_audio(frame, 320, None, None)
    src._on_audio(frame, 320, None, None)

    assert src.dropped_chunks == 1
