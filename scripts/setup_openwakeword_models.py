"""Download and verify openwakeword ONNX assets used by runtime-ai mode."""

from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path
import time
from typing import Sequence

import yaml


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and verify openwakeword ONNX model assets."
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Wake model name from openwakeword.MODELS. Repeat to pass multiple models.",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Config path used to resolve enabled wake rules when --model is omitted.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Max download retries for transient network failures.",
    )
    parser.add_argument(
        "--retry-sleep",
        type=float,
        default=1.5,
        help="Seconds to sleep between retries.",
    )
    return parser


def _download_url_with_retries(
    url: str, target_directory: Path, retries: int, retry_sleep: float
) -> None:
    from openwakeword.utils import download_file

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"[INFO] downloading {url.split('/')[-1]} attempt={attempt}/{retries}")
            download_file(url, str(target_directory))
            return
        except Exception as exc:
            last_error = exc
            print(f"[WARN] download failed {url} attempt={attempt}: {exc}")
            if attempt < retries:
                time.sleep(retry_sleep)

    if last_error is not None:
        raise last_error


def _resolve_model_names(cli_models: Sequence[str], config_path: str) -> list[str]:
    models = [str(item).strip() for item in cli_models if str(item).strip()]
    if models:
        return sorted(set(models))

    try:
        config_file = Path(config_path)
        if config_file.exists():
            loaded = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
            wake_rules = (
                loaded.get("wake", {}).get("rules", [])
                if isinstance(loaded.get("wake", {}), dict)
                else []
            )
            enabled = [
                str(rule.get("keyword", "")).strip()
                for rule in wake_rules
                if isinstance(rule, dict) and bool(rule.get("enabled", True))
            ]
            enabled = [item for item in enabled if item]
            if enabled:
                return sorted(set(enabled))
    except Exception:
        pass

    return [os.environ.get("ASR_OL_WAKE_MODEL", "alexa").strip() or "alexa"]


def _setup_assets(model_names: Sequence[str], retries: int, retry_sleep: float) -> Path:
    import openwakeword
    from openwakeword.utils import download_models

    known = set(openwakeword.MODELS)
    unknown = [name for name in model_names if name not in known]
    if unknown:
        known_names = ", ".join(sorted(known))
        missing = ", ".join(sorted(unknown))
        raise ValueError(f"unknown wake model(s) '{missing}', available: {known_names}")

    target_directory = Path(next(iter(openwakeword.MODELS.values()))["model_path"]).parent
    target_directory.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] prepare openwakeword assets models={list(model_names)}")
    download_models(model_names=list(model_names), target_directory=str(target_directory))

    required_urls = [
        model["download_url"].replace(".tflite", ".onnx")
        for model in openwakeword.FEATURE_MODELS.values()
    ]
    required_urls.extend(model["download_url"] for model in openwakeword.VAD_MODELS.values())
    required_urls.extend(
        openwakeword.MODELS[model_name]["download_url"].replace(".tflite", ".onnx")
        for model_name in model_names
    )

    for url in required_urls:
        filename = url.split("/")[-1]
        path = target_directory / filename
        if path.exists():
            continue
        _download_url_with_retries(
            url=url,
            target_directory=target_directory,
            retries=retries,
            retry_sleep=retry_sleep,
        )

    return target_directory


def _verify_onnx_runtime(model_names: Sequence[str]) -> None:
    import numpy as np
    from openwakeword.model import Model

    model = Model(wakeword_models=list(model_names), inference_framework="onnx")
    model.predict(np.zeros(1280, dtype=np.int16))


def main() -> int:
    """Prepare openwakeword assets and validate ONNX inference."""
    args = _build_parser().parse_args()
    print(f"python={platform.python_version()}")
    model_names = _resolve_model_names(cli_models=args.model, config_path=args.config)
    target_directory = _setup_assets(
        model_names=model_names,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
    )
    _verify_onnx_runtime(model_names=model_names)
    print(f"[PASS] openwakeword onnx assets ready models={model_names} dir={target_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
