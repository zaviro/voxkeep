from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path
import time


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and verify openwakeword ONNX model assets."
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("ASR_OL_WAKE_MODEL", "alexa"),
        help="Wake model name from openwakeword.MODELS (default: alexa).",
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


def _setup_assets(model_name: str, retries: int, retry_sleep: float) -> Path:
    import openwakeword
    from openwakeword.utils import download_models

    if model_name not in openwakeword.MODELS:
        known = ", ".join(sorted(openwakeword.MODELS))
        raise ValueError(f"unknown wake model '{model_name}', available: {known}")

    target_directory = Path(next(iter(openwakeword.MODELS.values()))["model_path"]).parent
    target_directory.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] prepare openwakeword assets model={model_name}")
    download_models(model_names=[model_name], target_directory=str(target_directory))

    required_urls = [
        model["download_url"].replace(".tflite", ".onnx")
        for model in openwakeword.FEATURE_MODELS.values()
    ]
    required_urls.extend(model["download_url"] for model in openwakeword.VAD_MODELS.values())
    required_urls.append(
        openwakeword.MODELS[model_name]["download_url"].replace(".tflite", ".onnx")
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


def _verify_onnx_runtime(model_name: str) -> None:
    import numpy as np
    from openwakeword.model import Model

    model = Model(wakeword_models=[model_name], inference_framework="onnx")
    model.predict(np.zeros(1280, dtype=np.int16))


def main() -> int:
    args = _build_parser().parse_args()
    print(f"python={platform.python_version()}")
    model_name = (args.model or "alexa").strip()
    target_directory = _setup_assets(
        model_name=model_name,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
    )
    _verify_onnx_runtime(model_name=model_name)
    print(f"[PASS] openwakeword onnx assets ready model={model_name} dir={target_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
