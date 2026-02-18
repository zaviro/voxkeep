from __future__ import annotations

import importlib
import platform
import sys


def _check_module(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return False, f"{type(exc).__name__}: {exc}"
    return True, "ok"


def main() -> int:
    print(f"python={platform.python_version()}")
    checks = ["openwakeword", "silero_vad"]
    failed = False

    for module_name in checks:
        ok, message = _check_module(module_name)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] import {module_name}: {message}")
        failed = failed or (not ok)

    if failed and sys.version_info >= (3, 12):
        print("hint: openwakeword is not available on cp312; use: uv run --python 3.11 ...")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
