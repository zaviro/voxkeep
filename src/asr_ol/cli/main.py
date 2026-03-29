"""CLI entrypoint for running the local ASR pipeline."""

from __future__ import annotations

import argparse
import logging

from asr_ol.core.config import load_config
from asr_ol.core.logging_setup import configure_logging
from asr_ol.bootstrap.runtime_app import AppRuntime
from asr_ol.services.shutdown import install_signal_handlers

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_RUNTIME_FAILURE = 2


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(description="Local ASR wake capture injector")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML config file",
    )
    return parser


def main() -> int:
    """Run CLI entrypoint and return process exit code.

    Returns:
        Exit code where `0` means normal shutdown and `2` means runtime fatal error.

    """
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

    if runtime.fatal_error is not None:
        logger.error("runtime terminated with fatal error: %s", runtime.fatal_error)
        return EXIT_RUNTIME_FAILURE

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
