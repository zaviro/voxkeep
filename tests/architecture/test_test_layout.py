from __future__ import annotations

from pathlib import Path


TESTS_ROOT = Path(__file__).resolve().parents[1] / "unit"
LEGACY_DIRS = ("core", "services", "infra", "agents", "tools")


def test_unit_tests_do_not_use_legacy_group_directories() -> None:
    existing = [name for name in LEGACY_DIRS if (TESTS_ROOT / name).exists()]
    assert existing == []
