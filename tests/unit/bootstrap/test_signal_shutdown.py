from __future__ import annotations

import signal
import threading

from voxkeep.bootstrap.shutdown import install_signal_handlers


def test_install_signal_handlers_registers_sigint_and_sigterm(monkeypatch) -> None:
    registered: dict[int, object] = {}

    def fake_signal(signum: int, handler: object) -> None:
        registered[signum] = handler

    monkeypatch.setattr(signal, "signal", fake_signal)

    install_signal_handlers(threading.Event())

    assert signal.SIGINT in registered
    assert signal.SIGTERM in registered


def test_signal_handler_sets_stop_event(monkeypatch) -> None:
    registered: dict[int, object] = {}
    stop_event = threading.Event()

    def fake_signal(signum: int, handler: object) -> None:
        registered[signum] = handler

    monkeypatch.setattr(signal, "signal", fake_signal)

    install_signal_handlers(stop_event)
    handler = registered[signal.SIGINT]
    handler(signal.SIGINT, None)  # type: ignore[operator]

    assert stop_event.is_set() is True
