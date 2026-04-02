"""Persistent ASR backend asset state helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def assets_state_path() -> Path:
    """Return the user-data path that stores backend installation state."""
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "voxkeep" / "backends" / "installed.json"


def read_assets_state() -> dict[str, Any]:
    """Read the persisted backend asset state, returning an empty mapping when absent."""
    path = assets_state_path()
    if not path.exists():
        return {}

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed installed.json at {path}: {exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("assets state root must be a mapping")
    return loaded


def write_assets_state(data: dict[str, Any]) -> None:
    """Persist backend asset state under the user data directory."""
    path = assets_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["assets_state_path", "read_assets_state", "write_assets_state"]
