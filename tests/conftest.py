from __future__ import annotations

import os
import shutil
from dataclasses import replace

import pytest

from voxkeep.shared.config import (
    AppConfig,
    AsrConfig,
    AudioEngineConfig,
    CaptureConfig,
    InjectorConfig,
    StorageConfig,
    WakeRuleConfig,
)


@pytest.fixture
def app_config() -> AppConfig:
    audio_engine = AudioEngineConfig(
        sample_rate=16000,
        channels=1,
        frame_ms=20,
        max_queue_size=16,
    )
    asr = AsrConfig(
        backend="qwen_vllm",
        mode="external",
        external_host="127.0.0.1",
        external_port=10096,
        external_path="/",
        use_ssl=False,
        reconnect_initial_s=1.0,
        reconnect_max_s=30.0,
        runtime_reconnect_initial_s=1.0,
        runtime_reconnect_max_s=30.0,
        qwen_model="Qwen/Qwen3-ASR-1.7B",
        qwen_realtime=True,
        qwen_gpu_memory_utilization=0.65,
        qwen_max_model_len=32768,
        max_queue_size=16,
        sample_rate=16000,
    )
    capture = CaptureConfig(
        wake_threshold=0.5,
        wake_rules=(
            WakeRuleConfig(
                keyword="alexa",
                enabled=True,
                threshold=0.5,
                action="inject_text",
            ),
            WakeRuleConfig(
                keyword="hey_jarvis",
                enabled=True,
                threshold=0.6,
                action="openclaw_agent",
            ),
        ),
        vad_speech_threshold=0.5,
        vad_silence_ms=800,
        pre_roll_ms=600,
        armed_timeout_ms=5000,
        max_queue_size=16,
    )
    storage = StorageConfig(
        sqlite_path=":memory:",
        store_final_only=True,
        jsonl_debug_path=None,
        max_queue_size=16,
    )
    injector = InjectorConfig(
        backend="auto",
        auto_enter=False,
        xdotool_delay_ms=1,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
        max_queue_size=16,
    )
    return AppConfig(
        audio_engine=audio_engine,
        asr=asr,
        capture=capture,
        storage=storage,
        injector=injector,
        log_level="INFO",
    )


@pytest.fixture
def qwen_app_config(app_config: AppConfig) -> AppConfig:
    new_asr = replace(
        app_config.asr,
        backend="qwen_vllm",
        external_port=8000,
        external_path="/v1/realtime",
        runtime_reconnect_initial_s=1.5,
        runtime_reconnect_max_s=12.0,
    )
    return replace(app_config, asr=new_asr)


@pytest.fixture
def require_openclaw_real() -> None:
    if os.environ.get("VOXKEEP_RUN_OPENCLAW_REAL") != "1":
        pytest.skip("set VOXKEEP_RUN_OPENCLAW_REAL=1 to run real OpenClaw integration tests")
    if shutil.which("openclaw") is None:
        pytest.skip("openclaw command not found in PATH")
