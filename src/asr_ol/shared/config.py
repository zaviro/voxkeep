"""Shared config re-export shim for stage-one migration."""

from asr_ol.core.config import AppConfig, WakeRuleConfig, load_config

__all__ = ["AppConfig", "WakeRuleConfig", "load_config"]
