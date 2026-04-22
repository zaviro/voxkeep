"""Injector backend factory for the injection module."""

from __future__ import annotations

import os

from voxkeep.shared.config import InjectorConfig
from voxkeep.modules.injection.infrastructure.base import Injector
from voxkeep.modules.injection.infrastructure.xdotool_injector import XdotoolInjector
from voxkeep.modules.injection.infrastructure.ydotool_injector import YdotoolInjector


def build_injector(cfg: InjectorConfig) -> Injector:
    """Build the configured injector backend."""
    backend = cfg.backend.lower()
    if backend == "auto":
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        backend = "ydotool" if session == "wayland" else "xdotool"

    if backend == "ydotool":
        return YdotoolInjector(auto_enter=cfg.auto_enter)

    return XdotoolInjector(
        delay_ms=cfg.xdotool_delay_ms,
        auto_enter=cfg.auto_enter,
    )
