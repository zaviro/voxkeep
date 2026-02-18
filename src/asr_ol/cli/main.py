from __future__ import annotations

import argparse
import logging

from asr_ol.core.config import load_config
from asr_ol.core.logging_setup import configure_logging
from asr_ol.services.runtime_app import AppRuntime
from asr_ol.services.shutdown import install_signal_handlers

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local ASR wake capture injector")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML config file",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    configure_logging(cfg.log_level)

    runtime = AppRuntime(cfg)
    install_signal_handlers(runtime.stop_event)

    try:
        runtime.start()
        runtime.run_forever()
    except KeyboardInterrupt:
        logger.info("keyboard interrupt")
    finally:
        runtime.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
