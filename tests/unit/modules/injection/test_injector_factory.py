from __future__ import annotations

from dataclasses import replace

import pytest

from voxkeep.shared.config import AppConfig
from voxkeep.modules.injection.infrastructure.factory import build_injector
from voxkeep.modules.injection.infrastructure.xdotool_injector import XdotoolInjector
from voxkeep.modules.injection.infrastructure.ydotool_injector import YdotoolInjector


@pytest.mark.parametrize(
    ("session_type", "backend", "expected_type"),
    [
        ("x11", "auto", XdotoolInjector),
        ("wayland", "auto", YdotoolInjector),
        ("x11", "ydotool", YdotoolInjector),
    ],
)
def test_factory_selects_backend(
    monkeypatch,
    app_config: AppConfig,
    session_type: str,
    backend: str,
    expected_type: type,
):
    monkeypatch.setenv("XDG_SESSION_TYPE", session_type)
    cfg = replace(app_config.injector, backend=backend)

    injector = build_injector(cfg)

    assert isinstance(injector, expected_type)
