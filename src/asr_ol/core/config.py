from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True, frozen=True)
class WakeRuleConfig:
    keyword: str
    enabled: bool
    threshold: float
    action: str


@dataclass(slots=True, frozen=True)
class AppConfig:
    sample_rate: int
    channels: int
    frame_ms: int
    max_queue_size: int
    funasr_host: str
    funasr_port: int
    funasr_path: str
    funasr_use_ssl: bool
    asr_reconnect_initial_s: float
    asr_reconnect_max_s: float
    wake_threshold: float
    wake_rules: tuple[WakeRuleConfig, ...]
    vad_speech_threshold: float
    vad_silence_ms: int
    pre_roll_ms: int
    armed_timeout_ms: int
    sqlite_path: str
    store_final_only: bool
    jsonl_debug_path: str | None
    injector_backend: str
    injector_auto_enter: bool
    xdotool_delay_ms: int
    openclaw_command: tuple[str, ...]
    openclaw_timeout_s: float
    log_level: str

    def __post_init__(self) -> None:
        _require_positive_int("sample_rate", self.sample_rate)
        _require_positive_int("channels", self.channels)
        _require_positive_int("frame_ms", self.frame_ms)
        _require_positive_int("max_queue_size", self.max_queue_size)
        _require_positive_int("funasr_port", self.funasr_port)
        _require_probability("wake_threshold", self.wake_threshold)
        _require_probability("vad_speech_threshold", self.vad_speech_threshold)
        _require_non_negative_int("pre_roll_ms", self.pre_roll_ms)
        _require_positive_int("armed_timeout_ms", self.armed_timeout_ms)
        _require_positive_int("vad_silence_ms", self.vad_silence_ms)
        _require_positive_float("asr_reconnect_initial_s", self.asr_reconnect_initial_s)
        _require_positive_float("asr_reconnect_max_s", self.asr_reconnect_max_s)
        if self.asr_reconnect_max_s < self.asr_reconnect_initial_s:
            raise ValueError("asr_reconnect_max_s must be >= asr_reconnect_initial_s")
        if not self.funasr_path.startswith("/"):
            raise ValueError("funasr_path must start with '/'")
        backend = self.injector_backend.strip().lower()
        if backend not in {"auto", "xdotool", "ydotool"}:
            raise ValueError("injector_backend must be one of: auto, xdotool, ydotool")
        _require_non_negative_int("xdotool_delay_ms", self.xdotool_delay_ms)
        _require_positive_float("openclaw_timeout_s", self.openclaw_timeout_s)
        if not self.openclaw_command:
            raise ValueError("openclaw_command must not be empty")
        if any(not part.strip() for part in self.openclaw_command):
            raise ValueError("openclaw_command contains empty parts")
        if not self.log_level.strip():
            raise ValueError("log_level must not be empty")
        _validate_wake_rules(self.wake_rules)

    @property
    def frame_samples(self) -> int:
        return int(self.sample_rate * (self.frame_ms / 1000.0))

    @property
    def asr_ws_url(self) -> str:
        schema = "wss" if self.funasr_use_ssl else "ws"
        return f"{schema}://{self.funasr_host}:{self.funasr_port}{self.funasr_path}"

    @property
    def enabled_wake_rules(self) -> tuple[WakeRuleConfig, ...]:
        return tuple(rule for rule in self.wake_rules if rule.enabled)


_DEFAULTS = {
    "sample_rate": 16000,
    "channels": 1,
    "frame_ms": 32,
    "max_queue_size": 512,
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


_ENV_MAP = {
    "ASR_OL_SAMPLE_RATE": ("sample_rate", int),
    "ASR_OL_CHANNELS": ("channels", int),
    "ASR_OL_FRAME_MS": ("frame_ms", int),
    "ASR_OL_MAX_QUEUE_SIZE": ("max_queue_size", int),
    "ASR_OL_FUNASR_HOST": ("funasr.host", str),
    "ASR_OL_FUNASR_PORT": ("funasr.port", int),
    "ASR_OL_FUNASR_PATH": ("funasr.path", str),
    "ASR_OL_FUNASR_USE_SSL": ("funasr.use_ssl", lambda v: v.lower() in {"1", "true", "yes", "on"}),
    "ASR_OL_ASR_RECONNECT_INITIAL_S": ("funasr.reconnect_initial_s", float),
    "ASR_OL_ASR_RECONNECT_MAX_S": ("funasr.reconnect_max_s", float),
    "ASR_OL_WAKE_THRESHOLD": ("wake.threshold", float),
    "ASR_OL_VAD_SPEECH_THRESHOLD": ("vad.speech_threshold", float),
    "ASR_OL_VAD_SILENCE_MS": ("vad.silence_ms", int),
    "ASR_OL_PRE_ROLL_MS": ("capture.pre_roll_ms", int),
    "ASR_OL_CAPTURE_ARMED_TIMEOUT_MS": ("capture.armed_timeout_ms", int),
    "ASR_OL_SQLITE_PATH": ("storage.sqlite_path", str),
    "ASR_OL_STORE_FINAL_ONLY": (
        "storage.store_final_only",
        lambda v: v.lower() in {"1", "true", "yes", "on"},
    ),
    "ASR_OL_JSONL_DEBUG_PATH": ("storage.jsonl_debug_path", str),
    "ASR_OL_INJECTOR_BACKEND": ("injector.backend", str),
    "ASR_OL_INJECTOR_AUTO_ENTER": (
        "injector.auto_enter",
        lambda v: v.lower() in {"1", "true", "yes", "on"},
    ),
    "ASR_OL_XDOTOOL_DELAY_MS": ("injector.xdotool_delay_ms", int),
    "ASR_OL_OPENCLAW_TIMEOUT_S": ("actions.openclaw_agent.timeout_s", float),
    "ASR_OL_LOG_LEVEL": ("runtime.log_level", str),
}


def _require_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _require_non_negative_int(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _require_positive_float(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _require_probability(name: str, value: float) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{name} must be between 0 and 1")


def _validate_wake_rules(rules: tuple[WakeRuleConfig, ...]) -> None:
    seen: set[str] = set()
    for rule in rules:
        keyword = rule.keyword.strip()
        if not keyword:
            raise ValueError("wake_rules contains empty keyword")
        if keyword in seen:
            raise ValueError(f"wake_rules contains duplicate keyword: {keyword}")
        seen.add(keyword)
        _require_probability("wake_rules.threshold", rule.threshold)
        if not rule.action.strip():
            raise ValueError(f"wake_rules[{keyword}] action must not be empty")


def _deep_copy_dict(obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in obj.items():
        if isinstance(value, dict):
            out[key] = _deep_copy_dict(value)
        else:
            out[key] = value
    return out


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _set_nested(conf: dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = conf
    for key in keys[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[keys[-1]] = value


def _apply_env(conf: dict[str, Any]) -> None:
    for env_key, (dest, caster) in _ENV_MAP.items():
        if env_key not in os.environ:
            continue
        raw = os.environ[env_key]
        _set_nested(conf, dest, caster(raw))


def _parse_wake_rules(data: dict[str, Any]) -> tuple[WakeRuleConfig, ...]:
    wake_conf = data.get("wake", {})
    default_threshold = float(wake_conf.get("threshold", 0.5))
    raw_rules = wake_conf.get("rules")
    if not raw_rules:
        default_model = os.environ.get("ASR_OL_WAKE_MODEL", "alexa").strip() or "alexa"
        raw_rules = [
            {
                "keyword": default_model,
                "enabled": True,
                "threshold": default_threshold,
                "action": "inject_text",
            }
        ]

    rules: list[WakeRuleConfig] = []
    seen_keywords: set[str] = set()
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword", "")).strip()
        if not keyword or keyword in seen_keywords:
            continue
        seen_keywords.add(keyword)
        rules.append(
            WakeRuleConfig(
                keyword=keyword,
                enabled=bool(item.get("enabled", True)),
                threshold=float(item.get("threshold", default_threshold)),
                action=str(item.get("action", "inject_text")).strip() or "inject_text",
            )
        )

    if not rules:
        rules.append(
            WakeRuleConfig(
                keyword="alexa",
                enabled=True,
                threshold=default_threshold,
                action="inject_text",
            )
        )

    return tuple(rules)


def _parse_openclaw_action(data: dict[str, Any]) -> tuple[tuple[str, ...], float]:
    actions = data.get("actions", {})
    openclaw_raw = actions.get("openclaw_agent", {}) if isinstance(actions, dict) else {}
    openclaw = openclaw_raw if isinstance(openclaw_raw, dict) else {}
    raw_command = openclaw.get("command", ["openclaw", "agent", "--message", "{text}"])
    if not isinstance(raw_command, list) or not raw_command:
        raw_command = ["openclaw", "agent", "--message", "{text}"]
    command = tuple(str(part) for part in raw_command)
    timeout = float(openclaw.get("timeout_s", 20.0))
    return command, timeout


def load_config(path: str | os.PathLike[str]) -> AppConfig:
    resolved = Path(path)
    data = _deep_copy_dict(_DEFAULTS)

    if resolved.exists():
        loaded = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        if loaded:
            _deep_merge(data, loaded)

    _apply_env(data)
    wake_rules = _parse_wake_rules(data)
    openclaw_command, openclaw_timeout_s = _parse_openclaw_action(data)

    jsonl_debug_path = data["storage"]["jsonl_debug_path"] or None
    return AppConfig(
        sample_rate=int(data["sample_rate"]),
        channels=int(data["channels"]),
        frame_ms=int(data["frame_ms"]),
        max_queue_size=int(data["max_queue_size"]),
        funasr_host=str(data["funasr"]["host"]),
        funasr_port=int(data["funasr"]["port"]),
        funasr_path=str(data["funasr"]["path"]),
        funasr_use_ssl=bool(data["funasr"]["use_ssl"]),
        asr_reconnect_initial_s=float(data["funasr"]["reconnect_initial_s"]),
        asr_reconnect_max_s=float(data["funasr"]["reconnect_max_s"]),
        wake_threshold=float(data["wake"]["threshold"]),
        wake_rules=wake_rules,
        vad_speech_threshold=float(data["vad"]["speech_threshold"]),
        vad_silence_ms=int(data["vad"]["silence_ms"]),
        pre_roll_ms=int(data["capture"]["pre_roll_ms"]),
        armed_timeout_ms=int(data["capture"]["armed_timeout_ms"]),
        sqlite_path=str(data["storage"]["sqlite_path"]),
        store_final_only=bool(data["storage"]["store_final_only"]),
        jsonl_debug_path=jsonl_debug_path,
        injector_backend=str(data["injector"]["backend"]),
        injector_auto_enter=bool(data["injector"]["auto_enter"]),
        xdotool_delay_ms=int(data["injector"]["xdotool_delay_ms"]),
        openclaw_command=openclaw_command,
        openclaw_timeout_s=openclaw_timeout_s,
        log_level=str(data["runtime"]["log_level"]),
    )
