from __future__ import annotations

import types

from asr_ol.cli import main as cli_main


class _Parser:
    def parse_args(self):  # type: ignore[no-untyped-def]
        return types.SimpleNamespace(config="config/config.yaml")


class _RuntimeBase:
    def __init__(self, _cfg) -> None:  # type: ignore[no-untyped-def]
        self.stop_event = types.SimpleNamespace()
        self.started = False
        self.stopped = False
        self._fatal_error: str | None = None

    @property
    def fatal_error(self) -> str | None:
        return self._fatal_error

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


class _RuntimeHealthy(_RuntimeBase):
    def run_forever(self) -> None:
        return


class _RuntimeFatal(_RuntimeBase):
    def run_forever(self) -> None:
        self._fatal_error = "worker stopped unexpectedly: asr_worker"


class _RuntimeKeyboard(_RuntimeBase):
    def run_forever(self) -> None:
        raise KeyboardInterrupt


def _setup_common(monkeypatch, runtime_cls: type[_RuntimeBase]) -> None:
    monkeypatch.setattr(cli_main, "build_arg_parser", lambda: _Parser())
    monkeypatch.setattr(
        cli_main, "load_config", lambda _path: types.SimpleNamespace(log_level="INFO")
    )
    monkeypatch.setattr(cli_main, "configure_logging", lambda _level: None)
    monkeypatch.setattr(cli_main, "install_signal_handlers", lambda _stop_event: None)
    monkeypatch.setattr(cli_main, "AppRuntime", runtime_cls)


def test_main_returns_zero_on_healthy_exit(monkeypatch):
    _setup_common(monkeypatch, _RuntimeHealthy)

    code = cli_main.main()

    assert code == cli_main.EXIT_OK


def test_main_returns_nonzero_on_runtime_fatal(monkeypatch):
    _setup_common(monkeypatch, _RuntimeFatal)

    code = cli_main.main()

    assert code == cli_main.EXIT_RUNTIME_FAILURE


def test_main_returns_zero_on_keyboard_interrupt(monkeypatch):
    _setup_common(monkeypatch, _RuntimeKeyboard)

    code = cli_main.main()

    assert code == cli_main.EXIT_OK


def test_cli_uses_bootstrap_runtime_app() -> None:
    assert cli_main.AppRuntime.__module__ == "asr_ol.bootstrap.runtime_app"
