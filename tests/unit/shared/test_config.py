from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from importlib import import_module

import pytest

from voxkeep.shared.config import AppConfig, WakeRuleConfig, load_config


def test_load_config_from_yaml_and_env(tmp_path, monkeypatch):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(
        "sample_rate: 16000\n"
        "channels: 1\n"
        "frame_ms: 20\n"
        "asr:\n"
        "  external:\n"
        "    host: 127.0.0.1\n"
        "    port: 10096\n"
        "wake:\n"
        "  threshold: 0.4\n"
        "  rules:\n"
        "    - keyword: alexa\n"
        "      enabled: true\n"
        "      action: inject_text\n"
        "    - keyword: hey_jarvis\n"
        "      enabled: true\n"
        "      threshold: 0.6\n"
        "      action: openclaw_agent\n"
        "actions:\n"
        "  openclaw_agent:\n"
        '    command: ["openclaw", "agent", "--message", "{text}"]\n'
        "    timeout_s: 21\n"
        "capture:\n"
        "  pre_roll_ms: 500\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VOXKEEP_PRE_ROLL_MS", "1500")
    cfg = load_config(str(cfg_file))

    assert isinstance(cfg, AppConfig)
    assert cfg.audio_engine.sample_rate == 16000
    assert cfg.audio_engine.frame_ms == 20
    assert cfg.capture.pre_roll_ms == 1500
    assert cfg.asr.backend == "qwen_vllm"
    assert cfg.asr.mode == "external"
    assert cfg.asr.external_host == "127.0.0.1"
    assert cfg.asr.external_port == 10096
    assert cfg.asr.external_path == "/"
    assert cfg.asr.use_ssl is False
    assert cfg.asr.qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.asr.qwen_realtime is True
    assert cfg.asr.qwen_gpu_memory_utilization == 0.65
    assert cfg.asr.qwen_max_model_len == 32768
    assert [rule.keyword for rule in cfg.capture.enabled_wake_rules] == ["alexa", "hey_jarvis"]
    assert cfg.capture.enabled_wake_rules[1].threshold == 0.6
    assert cfg.capture.enabled_wake_rules[1].action == "openclaw_agent"
    assert cfg.injector.openclaw_command == ("openclaw", "agent", "--message", "{text}")
    assert cfg.injector.openclaw_timeout_s == 21.0


def test_load_config_applies_new_asr_env_overrides(tmp_path, monkeypatch) -> None:
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("VOXKEEP_ASR_BACKEND", "qwen_vllm")
    monkeypatch.setenv("VOXKEEP_ASR_MODE", "external")
    monkeypatch.setenv("VOXKEEP_ASR_EXTERNAL_HOST", "10.0.0.7")
    monkeypatch.setenv("VOXKEEP_ASR_EXTERNAL_PORT", "11096")

    cfg = load_config(cfg_file)

    assert cfg.asr.backend == "qwen_vllm"
    assert cfg.asr.mode == "external"
    assert cfg.asr.external_host == "10.0.0.7"
    assert cfg.asr.external_port == 11096


def test_load_config_supports_qwen_backend_and_runtime_reconnect_settings(tmp_path) -> None:
    cfg_file = tmp_path / "qwen.yaml"
    cfg_file.write_text(
        "asr:\n"
        "  backend: qwen_vllm\n"
        "  mode: external\n"
        "  external:\n"
        "    host: 127.0.0.1\n"
        "    port: 8000\n"
        "    path: /v1/realtime\n"
        "    use_ssl: false\n"
        "  runtime:\n"
        "    reconnect_initial_s: 2.5\n"
        "    reconnect_max_s: 9.0\n",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.asr.backend == "qwen_vllm"
    assert cfg.asr.external_port == 8000
    assert cfg.asr.external_path == "/v1/realtime"
    assert cfg.asr.reconnect_initial_s == 2.5
    assert cfg.asr.reconnect_max_s == 9.0
    assert cfg.asr.runtime_reconnect_initial_s == 2.5
    assert cfg.asr.runtime_reconnect_max_s == 9.0


def test_load_config_supports_qwen_model_and_realtime_settings(tmp_path) -> None:
    cfg_file = tmp_path / "qwen-options.yaml"
    cfg_file.write_text(
        "asr:\n"
        "  backend: qwen_vllm\n"
        "  qwen:\n"
        "    model: Qwen/Qwen3-ASR-1.7B\n"
        "    realtime: true\n"
        "    gpu_memory_utilization: 0.65\n",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.asr.qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.asr.qwen_realtime is True
    assert cfg.asr.qwen_gpu_memory_utilization == 0.65
    assert cfg.asr.qwen_max_model_len == 32768


def test_load_config_supports_qwen_max_model_len_setting(tmp_path) -> None:
    cfg_file = tmp_path / "qwen-max-len.yaml"
    cfg_file.write_text(
        "asr:\n  qwen:\n    max_model_len: 24576\n",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.asr.qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.asr.qwen_max_model_len == 24576


def test_load_config_applies_runtime_reconnect_env_overrides(tmp_path, monkeypatch) -> None:
    cfg_file = tmp_path / "reconnect-env.yaml"
    cfg_file.write_text(
        "asr:\n  runtime:\n    reconnect_initial_s: 2.5\n    reconnect_max_s: 9.0\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("VOXKEEP_ASR_RUNTIME_RECONNECT_INITIAL_S", "3.25")
    monkeypatch.setenv("VOXKEEP_ASR_RUNTIME_RECONNECT_MAX_S", "11.5")

    cfg = load_config(cfg_file)

    assert cfg.asr.reconnect_initial_s == 3.25
    assert cfg.asr.reconnect_max_s == 11.5
    assert cfg.asr.runtime_reconnect_initial_s == 3.25
    assert cfg.asr.runtime_reconnect_max_s == 11.5


def test_app_config_is_frozen(app_config: AppConfig):
    with pytest.raises(FrozenInstanceError):
        app_config.log_level = "DEBUG"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        app_config.audio_engine.sample_rate = 8000  # type: ignore[misc]


@pytest.mark.parametrize(
    ("sub_config", "overrides", "match_text"),
    [
        ("audio_engine", {"sample_rate": 0}, "audio_engine.sample_rate"),
        ("audio_engine", {"max_queue_size": 0}, "audio_engine.max_queue_size"),
        ("capture", {"vad_speech_threshold": 1.5}, "capture.vad_speech_threshold"),
        ("asr", {"runtime_reconnect_max_s": 0.5}, "asr.runtime_reconnect_max_s"),
        ("asr", {"external_path": "not-slash"}, "asr.external_path"),
    ],
)
def test_app_config_validation_rejects_invalid_values(
    app_config: AppConfig,
    sub_config: str,
    overrides: dict[str, object],
    match_text: str,
):
    target = getattr(app_config, sub_config)
    new_sub = replace(target, **overrides)
    with pytest.raises(ValueError, match=match_text):
        replace(app_config, **{sub_config: new_sub})


def test_app_config_rejects_duplicate_wake_keywords(app_config: AppConfig) -> None:
    new_capture = replace(
        app_config.capture,
        wake_rules=(
            WakeRuleConfig("alexa", True, 0.5, "inject_text"),
            WakeRuleConfig("alexa", True, 0.6, "openclaw_agent"),
        ),
    )
    with pytest.raises(ValueError, match="duplicate keyword"):
        replace(app_config, capture=new_capture)


def test_app_config_rejects_empty_wake_keyword(app_config: AppConfig) -> None:
    new_capture = replace(
        app_config.capture,
        wake_rules=(WakeRuleConfig("", True, 0.5, "inject_text"),),
    )
    with pytest.raises(ValueError, match="empty keyword"):
        replace(app_config, capture=new_capture)


def test_app_config_rejects_empty_wake_action(app_config: AppConfig) -> None:
    new_capture = replace(
        app_config.capture,
        wake_rules=(WakeRuleConfig("alexa", True, 0.5, " "),),
    )
    with pytest.raises(ValueError, match="action must not be empty"):
        replace(app_config, capture=new_capture)


def test_load_config_raises_when_file_missing(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="config file not found"):
        load_config(tmp_path / "missing.yaml")


def test_load_config_raises_when_yaml_root_is_not_mapping(tmp_path) -> None:
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="config root must be a mapping"):
        load_config(cfg_file)


def test_load_config_raises_when_wake_rule_item_is_not_mapping(tmp_path) -> None:
    cfg_file = tmp_path / "bad_rules.yaml"
    cfg_file.write_text("wake:\n  rules:\n    - alexa\n", encoding="utf-8")

    with pytest.raises(ValueError, match="wake.rules items must be mappings"):
        load_config(cfg_file)


def test_enabled_wake_rules_filters_disabled_rules(app_config: AppConfig) -> None:
    new_capture = replace(
        app_config.capture,
        wake_rules=(
            WakeRuleConfig("alexa", True, 0.5, "inject_text"),
            WakeRuleConfig("hey_jarvis", False, 0.6, "openclaw_agent"),
        ),
    )
    cfg = replace(app_config, capture=new_capture)

    assert cfg.capture.enabled_wake_rules == (WakeRuleConfig("alexa", True, 0.5, "inject_text"),)


def test_frame_samples_property_is_derived_correctly(app_config: AppConfig) -> None:
    new_ae = replace(app_config.audio_engine, sample_rate=16000, frame_ms=32)
    cfg = replace(app_config, audio_engine=new_ae)

    assert cfg.audio_engine.frame_samples == 512


def test_asr_ws_url_uses_ws_or_wss_based_on_ssl(app_config: AppConfig) -> None:
    new_asr_ws = replace(app_config.asr, use_ssl=False)
    assert replace(app_config, asr=new_asr_ws).asr.ws_url.startswith("ws://")

    new_asr_wss = replace(app_config.asr, use_ssl=True)
    assert replace(app_config, asr=new_asr_wss).asr.ws_url.startswith("wss://")


def test_config_split_modules_reexport_public_api() -> None:
    schema = import_module("voxkeep.shared.config_schema")
    loader = import_module("voxkeep.shared.config_loader")

    assert schema.AppConfig is AppConfig
    assert schema.WakeRuleConfig is WakeRuleConfig
    assert loader.load_config is load_config
