from __future__ import annotations

import importlib
import os
import platform
import sys

import numpy as np


def _print_result(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")


def _check_module(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return False, f"{type(exc).__name__}: {exc}"
    return True, "ok"


def _check_openwakeword_onnx() -> tuple[bool, str]:
    model_name = os.environ.get("ASR_OL_WAKE_MODEL", "alexa").strip() or "alexa"
    try:
        from openwakeword.model import Model
    except Exception as exc:
        return False, f"import failed: {type(exc).__name__}: {exc}"

    try:
        model = Model(wakeword_models=[model_name], inference_framework="onnx")
        # 1280 samples (80ms @ 16k) is the nominal chunk size for openwakeword.
        model.predict(np.zeros(1280, dtype=np.int16))
    except Exception as exc:
        return False, f"onnx model init/predict failed: {type(exc).__name__}: {exc}"

    return True, f"onnx model init + predict ok model={model_name}"


def _check_silero_runtime() -> tuple[bool, str]:
    try:
        from silero_vad import load_silero_vad
    except Exception as exc:
        return False, f"import failed: {type(exc).__name__}: {exc}"

    try:
        import torch
    except Exception as exc:
        return False, f"torch import failed: {type(exc).__name__}: {exc}"

    try:
        model = load_silero_vad()
        frame = torch.from_numpy(np.zeros(512, dtype=np.float32)).unsqueeze(0)
        score = model(frame, 16000)
        _ = float(score.item()) if hasattr(score, "item") else score
    except Exception as exc:
        return False, f"silero init/predict failed: {type(exc).__name__}: {exc}"

    return True, "model init + predict ok"


def main() -> int:
    print(f"python={platform.python_version()}")
    failed = False

    for module_name in ["openwakeword", "silero_vad"]:
        ok, message = _check_module(module_name)
        _print_result(f"import {module_name}", ok, message)
        failed = failed or (not ok)

    wake_ok, wake_msg = _check_openwakeword_onnx()
    _print_result("openwakeword onnx runtime", wake_ok, wake_msg)
    failed = failed or (not wake_ok)

    vad_ok, vad_msg = _check_silero_runtime()
    _print_result("silero-vad runtime", vad_ok, vad_msg)
    failed = failed or (not vad_ok)

    if failed and sys.version_info >= (3, 12):
        print("hint: runtime-ai must run on Python 3.11 for this project.")
    if failed:
        print("hint: run 'make setup-ai-models' to download openwakeword model assets.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
