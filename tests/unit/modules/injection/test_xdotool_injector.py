from __future__ import annotations

import subprocess

from voxkeep.modules.injection.infrastructure.xdotool_injector import XdotoolInjector


def test_xdotool_injector_returns_false_for_blank_text() -> None:
    injector = XdotoolInjector()

    assert injector.inject("   ") is False


def test_xdotool_injector_runs_type_command_with_expected_args(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    injector = XdotoolInjector(delay_ms=7)

    assert injector.inject("hello") is True
    assert calls == [
        ["xdotool", "type", "--clearmodifiers", "--delay", "7", "--", "hello"],
    ]


def test_xdotool_injector_runs_return_key_when_auto_enter_enabled(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    injector = XdotoolInjector(auto_enter=True)

    assert injector.inject("hello") is True
    assert calls == [
        ["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", "hello"],
        ["xdotool", "key", "Return"],
    ]


def test_xdotool_injector_returns_false_when_subprocess_fails(monkeypatch) -> None:
    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    injector = XdotoolInjector()

    assert injector.inject("hello") is False
