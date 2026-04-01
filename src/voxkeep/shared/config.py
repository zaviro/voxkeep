"""Stable public exports for application configuration."""

from __future__ import annotations

from voxkeep.shared.config_loader import load_config
from voxkeep.shared.config_schema import AppConfig, WakeRuleConfig


__all__ = ["AppConfig", "WakeRuleConfig", "load_config"]
