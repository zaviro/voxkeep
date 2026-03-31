"""Application configuration loading, merging, and validation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True, frozen=True)
class WakeRuleConfig:
    """Wake keyword routing rule."""

    keyword: str
    enabled: bool
    threshold: float
    action: str


@dataclass(slots=True, frozen=True)
class AppConfig:
    """Immutable runtime configuration snapshot."""

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
        """Validate configuration values after dataclass construction."""
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
        """Return frame size in samples."""
        return int(self.sample_rate * (self.frame_ms / 1000.0))

    @property
    def asr_ws_url(self) -> str:
        """Return websocket endpoint URL assembled from FunASR settings."""
        schema = "wss" if self.funasr_use_ssl else "ws"
        return f"{schema}://{self.funasr_host}:{self.funasr_port}{self.funasr_path}"

    @property
    def enabled_wake_rules(self) -> tuple[WakeRuleConfig, ...]:
        """Return wake rules currently enabled."""
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
    "VOXKEEP_SAMPLE_RATE": ("sample_rate", int),
    "VOXKEEP_CHANNELS": ("channels", int),
    "VOXKEEP_FRAME_MS": ("frame_ms", int),
    "VOXKEEP_MAX_QUEUE_SIZE": ("max_queue_size", int),
    "VOXKEEP_FUNASR_HOST": ("funasr.host", str),
    "VOXKEEP_FUNASR_PORT": ("funasr.port", int),
    "VOXKEEP_FUNASR_PATH": ("funasr.path", str),
    "VOXKEEP_FUNASR_USE_SSL": ("funasr.use_ssl", lambda v: v.lower() in {"1", "true", "yes", "on"}),
    "VOXKEEP_ASR_RECONNECT_INITIAL_S": ("funasr.reconnect_initial_s", float),
    "VOXKEEP_ASR_RECONNECT_MAX_S": ("funasr.reconnect_max_s", float),
    "VOXKEEP_WAKE_THRESHOLD": ("wake.threshold", float),
    "VOXKEEP_VAD_SPEECH_THRESHOLD": ("vad.speech_threshold", float),
    "VOXKEEP_VAD_SILENCE_MS": ("vad.silence_ms", int),
    "VOXKEEP_PRE_ROLL_MS": ("capture.pre_roll_ms", int),
    "VOXKEEP_CAPTURE_ARMED_TIMEOUT_MS": ("capture.armed_timeout_ms", int),
    "VOXKEEP_SQLITE_PATH": ("storage.sqlite_path", str),
    "VOXKEEP_STORE_FINAL_ONLY": (
        "storage.store_final_only",
        lambda v: v.lower() in {"1", "true", "yes", "on"},
    ),
    "VOXKEEP_JSONL_DEBUG_PATH": ("storage.jsonl_debug_path", str),
    "VOXKEEP_INJECTOR_BACKEND": ("injector.backend", str),
    "VOXKEEP_INJECTOR_AUTO_ENTER": (
        "injector.auto_enter",
        lambda v: v.lower() in {"1", "true", "yes", "on"},
    ),
    "VOXKEEP_XDOTOOL_DELAY_MS": ("injector.xdotool_delay_ms", int),
    "VOXKEEP_OPENCLAW_TIMEOUT_S": ("actions.openclaw_agent.timeout_s", float),
    "VOXKEEP_LOG_LEVEL": ("runtime.log_level", str),
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


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return data


def _apply_env(conf: dict[str, Any]) -> dict[str, Any]:
    for env_name, (dotted, caster) in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        _set_nested(conf, dotted, caster(raw))
    return conf


def _parse_wake_rules(data: list[dict[str, Any]]) -> tuple[WakeRuleConfig, ...]:
    rules: list[WakeRuleConfig] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("wake.rules items must be mappings")
        rules.append(
            WakeRuleConfig(
                keyword=str(item.get("keyword", "")).strip(),
                enabled=bool(item.get("enabled", True)),
                threshold=float(item.get("threshold", 0.5)),
                action=str(item.get("action", "inject_text")).strip() or "inject_text",
            )
        )
    return tuple(rules)


def load_config(path: str | Path) -> AppConfig:
    """Load config from YAML file and environment variables."""
    merged = _deep_copy_dict(_DEFAULTS)
    merged = _deep_merge(merged, _load_yaml(Path(path)))
    merged = _apply_env(merged)

    wake = merged.get("wake", {})
    vad = merged.get("vad", {})
    capture = merged.get("capture", {})
    storage = merged.get("storage", {})
    injector = merged.get("injector", {})
    actions = merged.get("actions", {})
    runtime = merged.get("runtime", {})
    funasr = merged.get("funasr", {})

    openclaw = actions.get("openclaw_agent", {})
    command = tuple(str(part) for part in openclaw.get("command", []))

    return AppConfig(
        sample_rate=int(merged["sample_rate"]),
        channels=int(merged["channels"]),
        frame_ms=int(merged["frame_ms"]),
        max_queue_size=int(merged["max_queue_size"]),
        funasr_host=str(funasr["host"]),
        funasr_port=int(funasr["port"]),
        funasr_path=str(funasr["path"]),
        funasr_use_ssl=bool(funasr["use_ssl"]),
        asr_reconnect_initial_s=float(funasr["reconnect_initial_s"]),
        asr_reconnect_max_s=float(funasr["reconnect_max_s"]),
        wake_threshold=float(wake["threshold"]),
        wake_rules=_parse_wake_rules(list(wake.get("rules", []))),
        vad_speech_threshold=float(vad["speech_threshold"]),
        vad_silence_ms=int(vad["silence_ms"]),
        pre_roll_ms=int(capture["pre_roll_ms"]),
        armed_timeout_ms=int(capture["armed_timeout_ms"]),
        sqlite_path=str(storage["sqlite_path"]),
        store_final_only=bool(storage["store_final_only"]),
        jsonl_debug_path=str(storage.get("jsonl_debug_path") or "") or None,
        injector_backend=str(injector["backend"]),
        injector_auto_enter=bool(injector["auto_enter"]),
        xdotool_delay_ms=int(injector["xdotool_delay_ms"]),
        openclaw_command=command,
        openclaw_timeout_s=float(openclaw["timeout_s"]),
        log_level=str(runtime["log_level"]),
    )


__all__ = ["AppConfig", "WakeRuleConfig", "load_config"]
