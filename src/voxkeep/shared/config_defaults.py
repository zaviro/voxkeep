"""Default configuration values."""

from __future__ import annotations


DEFAULTS = {
    "sample_rate": 16000,
    "channels": 1,
    "frame_ms": 32,
    "max_queue_size": 512,
    "asr": {
        "backend": "funasr_ws_external",
        "mode": "auto",
        "external": {
            "host": "127.0.0.1",
            "port": 10096,
            "path": "/",
            "use_ssl": False,
        },
        "runtime": {
            "reconnect_initial_s": 1.0,
            "reconnect_max_s": 30.0,
        },
        "qwen": {
            "model": "Qwen/Qwen3-ASR-1.7B",
            "realtime": True,
            "gpu_memory_utilization": 0.65,
            "max_model_len": 32768,
        },
        "managed": {
            "provider": "docker",
            "image": "registry.cn-hangzhou.aliyuncs.com/"
            "funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13",
            "service_name": "funasr",
            "expose_port": 10096,
            "models_dir": "~/.local/share/voxkeep/models/funasr",
        },
    },
    "funasr": {
        "host": "127.0.0.1",
        "port": 10096,
        "path": "/",
        "use_ssl": False,
        "reconnect_initial_s": 1.0,
        "reconnect_max_s": 30.0,
    },
    "wake": {
        "threshold": 0.5,
        "rules": [
            {"keyword": "alexa", "enabled": True, "threshold": 0.5, "action": "inject_text"},
            {
                "keyword": "hey_jarvis",
                "enabled": True,
                "threshold": 0.5,
                "action": "openclaw_agent",
            },
            {
                "keyword": "hey_mycroft",
                "enabled": False,
                "threshold": 0.5,
                "action": "inject_text",
            },
            {
                "keyword": "hey_rhasspy",
                "enabled": False,
                "threshold": 0.5,
                "action": "inject_text",
            },
            {"keyword": "timer", "enabled": False, "threshold": 0.5, "action": "inject_text"},
            {
                "keyword": "weather",
                "enabled": False,
                "threshold": 0.5,
                "action": "inject_text",
            },
        ],
    },
    "vad": {"speech_threshold": 0.5, "silence_ms": 800},
    "capture": {"pre_roll_ms": 600, "armed_timeout_ms": 5000},
    "storage": {
        "sqlite_path": "data/asr.db",
        "store_final_only": True,
        "jsonl_debug_path": "",
    },
    "injector": {
        "backend": "auto",
        "auto_enter": False,
        "xdotool_delay_ms": 1,
    },
    "actions": {
        "openclaw_agent": {
            "command": ["openclaw", "agent", "--message", "{text}"],
            "timeout_s": 20.0,
        }
    },
    "runtime": {"log_level": "INFO"},
}


__all__ = ["DEFAULTS"]
