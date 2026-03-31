"""CLI entrypoint for running the local ASR pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

from asr_ol.shared.config import load_config
from asr_ol.shared.logging_setup import configure_logging
from asr_ol.bootstrap.runtime_app import AppRuntime
from asr_ol.bootstrap.shutdown import install_signal_handlers

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_COMMAND_FAILURE = 1
EXIT_RUNTIME_FAILURE = 2
_ROOT_HELP_FLAGS = {"-h", "--help"}
_SUBCOMMANDS = {"run", "doctor", "check", "config"}
_PYTHON_MODULE_TOOLS = {"pytest", "pyright", "ruff"}


def normalize_cli_argv(argv: Sequence[str] | None) -> list[str]:
    """Normalize argv while preserving legacy `asr-ol --config ...` usage."""
    normalized = list(sys.argv[1:] if argv is None else argv)
    if not normalized:
        return ["run"]
    if normalized[0] in _SUBCOMMANDS or normalized[0] in _ROOT_HELP_FLAGS:
        return normalized
    return ["run", *normalized]


def _project_root() -> Path:
    """Return repository root for repo-local helper commands."""
    return Path(__file__).resolve().parents[3]


def _repo_path(*parts: str) -> Path:
    path = _project_root().joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(f"required repository path not found: {path}")
    return path


def _dev_command(*args: str) -> list[str]:
    """Build a development command, preferring uv when available."""
    command = list(args)
    if command and command[0] in _PYTHON_MODULE_TOOLS:
        command = ["python", "-m", *command]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--python", "3.11", *command]
    return command


def _run_repo_command(command: list[str]) -> int:
    completed = subprocess.run(command, check=False, cwd=_project_root())
    return completed.returncode


def _run_runtime(cfg_path: str) -> int:
    cfg = load_config(cfg_path)
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


def _cmd_run(args: argparse.Namespace) -> int:
    return _run_runtime(args.config)


def _cmd_doctor(_args: argparse.Namespace) -> int:
    script = _repo_path("scripts", "check_env.sh")
    return _run_repo_command([str(script)])


def _cmd_check(_args: argparse.Namespace) -> int:
    commands = [
        _dev_command("ruff", "check", "src", "tests", "scripts"),
        _dev_command("pyright"),
        _dev_command("pytest", "-q"),
    ]
    for command in commands:
        exit_code = _run_repo_command(command)
        if exit_code != EXIT_OK:
            return exit_code
    return EXIT_OK


def _cmd_config_validate(args: argparse.Namespace) -> int:
    load_config(args.config)
    print(f"Config OK: {args.config}")
    return EXIT_OK


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(description="Local ASR wake capture injector")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to YAML config file",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser(
        "run",
        parents=[common],
        help="Run the local ASR runtime",
        description="Run the local ASR runtime",
    )
    run_parser.set_defaults(func=_cmd_run)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run local environment diagnostics",
        description="Run local environment diagnostics",
    )
    doctor_parser.set_defaults(func=_cmd_doctor)

    check_parser = subparsers.add_parser(
        "check",
        help="Run local developer quality checks",
        description="Run local developer quality checks",
    )
    check_parser.set_defaults(func=_cmd_check)

    config_parser = subparsers.add_parser(
        "config",
        help="Config helpers",
        description="Config helpers",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_subparsers.add_parser(
        "validate",
        parents=[common],
        help="Validate the YAML config file",
        description="Validate the YAML config file",
    )
    validate_parser.set_defaults(func=_cmd_config_validate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run CLI entrypoint and return process exit code.

    Returns:
        Exit code where `0` means success, `1` means command/config failure,
        and `2` means runtime fatal error.

    """
    parser = build_arg_parser()
    try:
        args = parser.parse_args(normalize_cli_argv(argv))
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
