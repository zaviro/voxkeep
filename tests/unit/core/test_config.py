from asr_ol.core.config import AppConfig, load_config


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
    monkeypatch.setenv("ASR_OL_PRE_ROLL_MS", "1500")
    cfg = load_config(str(cfg_file))

    assert isinstance(cfg, AppConfig)
    assert cfg.sample_rate == 16000
    assert cfg.frame_ms == 20
    assert cfg.pre_roll_ms == 1500
    assert cfg.funasr_host == "127.0.0.1"
    assert cfg.funasr_port == 10096
    assert [rule.keyword for rule in cfg.enabled_wake_rules] == ["alexa", "hey_jarvis"]
    assert cfg.enabled_wake_rules[1].threshold == 0.6
    assert cfg.enabled_wake_rules[1].action == "openclaw_agent"
    assert cfg.openclaw_command == ("openclaw", "agent", "--message", "{text}")
    assert cfg.openclaw_timeout_s == 21.0
