"""Configuration loading and merge helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from voxkeep.shared.config_defaults import DEFAULTS
from voxkeep.shared.config_env import ENV_MAP
from voxkeep.shared.config_schema import AppConfig, WakeRuleConfig


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


def _get_nested(conf: dict[str, Any], dotted: str) -> Any:
    cur: Any = conf
    for key in dotted.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return data


def _apply_env(conf: dict[str, Any]) -> dict[str, Any]:
    for env_name, (dotted, caster) in ENV_MAP.items():
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
    user_conf = _load_yaml(Path(path))
    merged = _deep_copy_dict(DEFAULTS)
    merged = _deep_merge(merged, user_conf)
    merged = _apply_env(merged)

    wake = merged.get("wake", {})
    vad = merged.get("vad", {})
    capture = merged.get("capture", {})
    storage = merged.get("storage", {})
    injector = merged.get("injector", {})
    actions = merged.get("actions", {})
    runtime = merged.get("runtime", {})
    asr = merged.get("asr", {})
    external = asr.get("external", {})
    asr_runtime = asr.get("runtime", {})
    qwen = asr.get("qwen", {})

    openclaw = actions.get("openclaw_agent", {})
    command = tuple(str(part) for part in openclaw.get("command", []))

    reconnect_initial_s = float(asr_runtime.get("reconnect_initial_s", 1.0))
    reconnect_max_s = float(asr_runtime.get("reconnect_max_s", 30.0))

    return AppConfig(
        sample_rate=int(merged["sample_rate"]),
        channels=int(merged["channels"]),
        frame_ms=int(merged["frame_ms"]),
        max_queue_size=int(merged["max_queue_size"]),
        asr_reconnect_initial_s=reconnect_initial_s,
        asr_reconnect_max_s=reconnect_max_s,
        asr_backend=str(asr["backend"]),
        asr_mode=str(asr["mode"]),
        asr_external_host=str(external["host"]),
        asr_external_port=int(external["port"]),
        asr_external_path=str(external["path"]),
        asr_external_use_ssl=bool(external["use_ssl"]),
        asr_runtime_reconnect_initial_s=reconnect_initial_s,
        asr_runtime_reconnect_max_s=reconnect_max_s,
        asr_qwen_model=str(qwen["model"]),
        asr_qwen_realtime=bool(qwen["realtime"]),
        asr_qwen_gpu_memory_utilization=float(qwen["gpu_memory_utilization"]),
        asr_qwen_max_model_len=int(qwen["max_model_len"]),
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


__all__ = ["load_config"]
