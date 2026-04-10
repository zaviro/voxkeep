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
        "funasr:\n"
        "  host: 127.0.0.1\n"
        "  port: 10096\n"
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
    assert cfg.sample_rate == 16000
    assert cfg.frame_ms == 20
    assert cfg.pre_roll_ms == 1500
    assert cfg.funasr_host == "127.0.0.1"
    assert cfg.funasr_port == 10096
    assert cfg.asr_backend == "funasr_ws_external"
    assert cfg.asr_mode == "auto"
    assert cfg.asr_external_host == "127.0.0.1"
    assert cfg.asr_external_port == 10096
    assert cfg.asr_external_path == "/"
    assert cfg.asr_external_use_ssl is False
    assert cfg.asr_qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.asr_qwen_realtime is True
    assert cfg.asr_qwen_gpu_memory_utilization == 0.65
    assert cfg.asr_qwen_max_model_len == 32768
    assert cfg.asr_managed_image == (
        "registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13"
    )
    assert [rule.keyword for rule in cfg.enabled_wake_rules] == ["alexa", "hey_jarvis"]
    assert cfg.enabled_wake_rules[1].threshold == 0.6
    assert cfg.enabled_wake_rules[1].action == "openclaw_agent"
    assert cfg.openclaw_command == ("openclaw", "agent", "--message", "{text}")
    assert cfg.openclaw_timeout_s == 21.0


def test_load_config_maps_legacy_funasr_fields_to_asr_backend(tmp_path) -> None:
    cfg_file = tmp_path / "legacy.yaml"
    cfg_file.write_text(
        "funasr:\n"
        "  host: 127.0.0.1\n"
        "  port: 10096\n"
        "  path: /socket\n"
        "  use_ssl: true\n"
        "  reconnect_initial_s: 1.5\n"
        "  reconnect_max_s: 12.0\n",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.asr_backend == "funasr_ws_external"
    assert cfg.asr_mode == "auto"
    assert cfg.asr_external_host == "127.0.0.1"
    assert cfg.asr_external_port == 10096
    assert cfg.asr_external_path == "/socket"
    assert cfg.asr_external_use_ssl is True
    assert cfg.funasr_host == "127.0.0.1"
    assert cfg.funasr_port == 10096
    assert cfg.funasr_path == "/socket"
    assert cfg.funasr_use_ssl is True
    assert cfg.asr_reconnect_initial_s == 1.5
    assert cfg.asr_reconnect_max_s == 12.0
    assert cfg.asr_runtime_reconnect_initial_s == 1.5
    assert cfg.asr_runtime_reconnect_max_s == 12.0


def test_load_config_applies_new_asr_env_overrides(tmp_path, monkeypatch) -> None:
    cfg_file = tmp_path / "env.yaml"
    cfg_file.write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("VOXKEEP_ASR_BACKEND", "funasr_ws_managed")
    monkeypatch.setenv("VOXKEEP_ASR_MODE", "managed")
    monkeypatch.setenv("VOXKEEP_ASR_EXTERNAL_HOST", "10.0.0.7")
    monkeypatch.setenv("VOXKEEP_ASR_EXTERNAL_PORT", "11096")
    monkeypatch.setenv("VOXKEEP_ASR_MANAGED_IMAGE", "example.com/funasr:1")

    cfg = load_config(cfg_file)

    assert cfg.asr_backend == "funasr_ws_managed"
    assert cfg.asr_mode == "managed"
    assert cfg.asr_external_host == "10.0.0.7"
    assert cfg.asr_external_port == 11096
    assert cfg.asr_managed_image == "example.com/funasr:1"


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

    assert cfg.asr_backend == "qwen_vllm"
    assert cfg.asr_external_port == 8000
    assert cfg.asr_external_path == "/v1/realtime"
    assert cfg.asr_reconnect_initial_s == 2.5
    assert cfg.asr_reconnect_max_s == 9.0
    assert cfg.asr_runtime_reconnect_initial_s == 2.5
    assert cfg.asr_runtime_reconnect_max_s == 9.0


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

    assert cfg.asr_qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.asr_qwen_realtime is True
    assert cfg.asr_qwen_gpu_memory_utilization == 0.65
    assert cfg.asr_qwen_max_model_len == 32768


def test_load_config_supports_qwen_max_model_len_setting(tmp_path) -> None:
    cfg_file = tmp_path / "qwen-max-len.yaml"
    cfg_file.write_text(
        "asr:\n  qwen:\n    max_model_len: 24576\n",
        encoding="utf-8",
    )

    cfg = load_config(cfg_file)

    assert cfg.asr_qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.asr_qwen_max_model_len == 24576


def test_load_config_applies_runtime_reconnect_env_overrides(tmp_path, monkeypatch) -> None:
    cfg_file = tmp_path / "reconnect-env.yaml"
    cfg_file.write_text(
        "funasr:\n"
        "  reconnect_initial_s: 1.5\n"
        "  reconnect_max_s: 12.0\n"
        "asr:\n"
        "  runtime:\n"
        "    reconnect_initial_s: 2.5\n"
        "    reconnect_max_s: 9.0\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("VOXKEEP_ASR_RUNTIME_RECONNECT_INITIAL_S", "3.25")
    monkeypatch.setenv("VOXKEEP_ASR_RUNTIME_RECONNECT_MAX_S", "11.5")

    cfg = load_config(cfg_file)

    assert cfg.asr_reconnect_initial_s == 3.25
    assert cfg.asr_reconnect_max_s == 11.5
    assert cfg.asr_runtime_reconnect_initial_s == 3.25
    assert cfg.asr_runtime_reconnect_max_s == 11.5


def test_app_config_is_frozen(app_config: AppConfig):
    with pytest.raises(FrozenInstanceError):
        app_config.sample_rate = 8000  # type: ignore[misc]


@pytest.mark.parametrize(
    ("overrides", "match_text"),
    [
        ({"sample_rate": 0}, "sample_rate"),
        ({"max_queue_size": 0}, "max_queue_size"),
        ({"vad_speech_threshold": 1.5}, "vad_speech_threshold"),
        ({"asr_reconnect_max_s": 0.5}, "asr_reconnect_max_s"),
        ({"funasr_path": "not-slash"}, "funasr_path"),
    ],
)
def test_app_config_validation_rejects_invalid_values(
    app_config: AppConfig,
    overrides: dict[str, object],
    match_text: str,
):
    with pytest.raises(ValueError, match=match_text):
        replace(app_config, **overrides)


def test_app_config_rejects_duplicate_wake_keywords(app_config: AppConfig) -> None:
    with pytest.raises(ValueError, match="duplicate keyword"):
        replace(
            app_config,
            wake_rules=(
                WakeRuleConfig("alexa", True, 0.5, "inject_text"),
                WakeRuleConfig("alexa", True, 0.6, "openclaw_agent"),
            ),
        )


def test_app_config_rejects_empty_wake_keyword(app_config: AppConfig) -> None:
    with pytest.raises(ValueError, match="empty keyword"):
        replace(
            app_config,
            wake_rules=(WakeRuleConfig("", True, 0.5, "inject_text"),),
        )


def test_app_config_rejects_empty_wake_action(app_config: AppConfig) -> None:
    with pytest.raises(ValueError, match="action must not be empty"):
        replace(
            app_config,
            wake_rules=(WakeRuleConfig("alexa", True, 0.5, " "),),
        )


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
    cfg = replace(
        app_config,
        wake_rules=(
            WakeRuleConfig("alexa", True, 0.5, "inject_text"),
            WakeRuleConfig("hey_jarvis", False, 0.6, "openclaw_agent"),
        ),
    )

    assert cfg.enabled_wake_rules == (WakeRuleConfig("alexa", True, 0.5, "inject_text"),)


def test_frame_samples_property_is_derived_correctly(app_config: AppConfig) -> None:
    cfg = replace(app_config, sample_rate=16000, frame_ms=32)

    assert cfg.frame_samples == 512


def test_asr_ws_url_uses_ws_or_wss_based_on_ssl(app_config: AppConfig) -> None:
    assert replace(app_config, funasr_use_ssl=False).asr_ws_url == "ws://127.0.0.1:10096/"
    assert replace(app_config, funasr_use_ssl=True).asr_ws_url == "wss://127.0.0.1:10096/"


def test_asr_ws_url_tracks_new_asr_external_fields(app_config: AppConfig) -> None:
    cfg = replace(
        app_config,
        asr_external_host="10.0.0.9",
        asr_external_port=20000,
        asr_external_path="/socket",
        asr_external_use_ssl=True,
    )

    assert cfg.asr_ws_url == "wss://10.0.0.9:20000/socket"
    assert cfg.funasr_host == "10.0.0.9"
    assert cfg.funasr_port == 20000
    assert cfg.funasr_path == "/socket"
    assert cfg.funasr_use_ssl is True


def test_asr_ws_url_uses_managed_backend_endpoint(app_config: AppConfig) -> None:
    cfg = replace(
        app_config,
        asr_backend="funasr_ws_managed",
        asr_external_host="10.0.0.9",
        asr_external_port=20000,
        asr_external_path="/socket",
        asr_external_use_ssl=True,
        asr_managed_expose_port=18080,
    )

    assert cfg.asr_ws_url == "ws://127.0.0.1:18080/socket"


def test_asr_backend_and_mode_are_canonicalized(app_config: AppConfig) -> None:
    cfg = replace(
        app_config,
        asr_backend="  FUNASR_WS_MANAGED  ",
        asr_mode="  MANAGED  ",
    )

    assert cfg.asr_backend == "funasr_ws_managed"
    assert cfg.asr_mode == "managed"


def test_qwen_app_config_fixture_supports_qwen_backend(qwen_app_config: AppConfig) -> None:
    assert qwen_app_config.asr_backend == "qwen_vllm"
    assert qwen_app_config.asr_external_port == 8000
    assert qwen_app_config.asr_external_path == "/v1/realtime"
    assert qwen_app_config.asr_runtime_reconnect_initial_s == 1.5
    assert qwen_app_config.asr_runtime_reconnect_max_s == 12.0


def test_config_split_modules_reexport_public_api() -> None:
    schema = import_module("voxkeep.shared.config_schema")
    loader = import_module("voxkeep.shared.config_loader")

    assert schema.AppConfig is AppConfig
    assert schema.WakeRuleConfig is WakeRuleConfig
    assert loader.load_config is load_config
