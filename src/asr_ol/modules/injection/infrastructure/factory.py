"""Injector backend factory for the injection module."""

from __future__ import annotations

import os

from asr_ol.shared.config import AppConfig
from asr_ol.modules.injection.infrastructure.base import Injector
from asr_ol.modules.injection.infrastructure.xdotool_injector import XdotoolInjector
from asr_ol.modules.injection.infrastructure.ydotool_injector import YdotoolInjector


def build_injector(cfg: AppConfig) -> Injector:
    """Build the configured injector backend."""
    backend = cfg.injector_backend.lower()
    if backend == "auto":
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        backend = "ydotool" if session == "wayland" else "xdotool"

    if backend == "ydotool":
        return YdotoolInjector(auto_enter=cfg.injector_auto_enter)

    return XdotoolInjector(
        delay_ms=cfg.xdotool_delay_ms,
        auto_enter=cfg.injector_auto_enter,
    )
