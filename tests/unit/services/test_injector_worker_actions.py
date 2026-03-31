from __future__ import annotations

import queue
import subprocess
import threading

import pytest

from voxkeep.shared.events import CaptureCommand
from voxkeep.modules.injection.infrastructure.injector_worker import InjectorWorker


class FakeInjector:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def inject(self, text: str) -> bool:
        self.texts.append(text)
        return True


def test_execute_action_routes_to_injector(monkeypatch):
    injector = FakeInjector()
    worker = InjectorWorker(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        injector=injector,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
    )

    cmd = CaptureCommand(
        session_id=1,
        keyword="alexa",
        action="inject_text",
        text="hello",
        start_ts=1.0,
        end_ts=2.0,
    )
    ok = worker._execute_action(cmd)

    assert ok is True
    assert injector.texts == ["hello"]


def test_execute_action_routes_to_openclaw(monkeypatch):
    injector = FakeInjector()
    called: dict[str, object] = {}

    def _fake_run(argv, check, timeout):  # type: ignore[no-untyped-def]
        called["argv"] = argv
        called["check"] = check
        called["timeout"] = timeout
        return 0

    monkeypatch.setattr("subprocess.run", _fake_run)
    worker = InjectorWorker(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        injector=injector,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=15.0,
    )

    cmd = CaptureCommand(
        session_id=2,
        keyword="hey_jarvis",
        action="openclaw_agent",
        text="你好",
        start_ts=1.0,
        end_ts=2.0,
    )
    ok = worker._execute_action(cmd)

    assert ok is True
    assert injector.texts == []
    assert called["argv"] == ["openclaw", "agent", "--message", "你好"]
    assert called["check"] is True
    assert called["timeout"] == 15.0


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("openclaw"),
        subprocess.TimeoutExpired(cmd=["openclaw"], timeout=1.0),
        subprocess.CalledProcessError(returncode=1, cmd=["openclaw"]),
    ],
)
def test_run_openclaw_agent_handles_subprocess_failures(monkeypatch, error: Exception):
    injector = FakeInjector()

    def _fake_run(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise error

    monkeypatch.setattr("subprocess.run", _fake_run)
    worker = InjectorWorker(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        injector=injector,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=10.0,
    )

    ok = worker._run_openclaw_agent("test")

    assert ok is False
