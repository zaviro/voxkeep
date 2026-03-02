from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from asr_ol.core.config import AppConfig, WakeRuleConfig


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        sample_rate=16000,
        channels=1,
        frame_ms=20,
        max_queue_size=16,
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
        sqlite_path=":memory:",
        store_final_only=True,
        jsonl_debug_path=None,
        injector_backend="auto",
        injector_auto_enter=False,
        xdotool_delay_ms=1,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
        log_level="INFO",
    )


@pytest.fixture
def app_config_factory(app_config: AppConfig):
    def _factory(**overrides: Any) -> AppConfig:
        return replace(app_config, **overrides)

    return _factory
