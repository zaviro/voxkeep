from __future__ import annotations

import subprocess

from voxkeep.modules.injection.infrastructure.ydotool_injector import YdotoolInjector


def test_ydotool_injector_returns_false_for_blank_text() -> None:
    injector = YdotoolInjector()

    assert injector.inject("   ") is False


def test_ydotool_injector_runs_type_command(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    injector = YdotoolInjector()

    assert injector.inject("hello") is True
    assert calls == [["ydotool", "type", "hello"]]


def test_ydotool_injector_runs_return_key_when_auto_enter_enabled(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    injector = YdotoolInjector(auto_enter=True)

    assert injector.inject("hello") is True
    assert calls == [
        ["ydotool", "type", "hello"],
        ["ydotool", "key", "28:1", "28:0"],
    ]


def test_ydotool_injector_returns_false_when_subprocess_fails(monkeypatch) -> None:
    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    injector = YdotoolInjector()

    assert injector.inject("hello") is False
