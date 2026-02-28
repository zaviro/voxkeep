from asr_ol.core.config import AppConfig, WakeRuleConfig
from asr_ol.tools.injector.factory import build_injector
from asr_ol.tools.injector.xdotool_injector import XdotoolInjector
from asr_ol.tools.injector.ydotool_injector import YdotoolInjector


def _cfg(backend: str) -> AppConfig:
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
        ),
        vad_speech_threshold=0.5,
        vad_silence_ms=800,
        pre_roll_ms=600,
        armed_timeout_ms=5000,
        sqlite_path=":memory:",
        store_final_only=True,
        jsonl_debug_path=None,
        injector_backend=backend,
        injector_auto_enter=False,
        xdotool_delay_ms=1,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
        log_level="INFO",
    )


def test_factory_selects_xdotool_under_x11(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    injector = build_injector(_cfg("auto"))
    assert isinstance(injector, XdotoolInjector)


def test_factory_selects_ydotool_under_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    injector = build_injector(_cfg("auto"))
    assert isinstance(injector, YdotoolInjector)


def test_factory_respects_explicit_backend(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    injector = build_injector(_cfg("ydotool"))
    assert isinstance(injector, YdotoolInjector)
