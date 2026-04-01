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


def test_execute_action_returns_false_for_unknown_action():
    injector = FakeInjector()
    worker = InjectorWorker(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        injector=injector,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
    )

    cmd = CaptureCommand(
        session_id=3,
        keyword="alexa",
        action="unknown_action",
        text="hello",
        start_ts=1.0,
        end_ts=2.0,
    )

    assert worker._execute_action(cmd) is False
    assert injector.texts == []


def test_run_openclaw_agent_appends_text_when_placeholder_missing(monkeypatch):
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
        openclaw_command=("openclaw", "agent"),
        openclaw_timeout_s=12.0,
    )

    assert worker._run_openclaw_agent("hello") is True
    assert called["argv"] == ["openclaw", "agent", "hello"]
    assert called["check"] is True
    assert called["timeout"] == 12.0


def test_injector_worker_run_drains_queue_before_exit(monkeypatch):
    injector = FakeInjector()
    stop_event = threading.Event()
    in_queue: queue.Queue[CaptureCommand] = queue.Queue()
    worker = InjectorWorker(
        in_queue=in_queue,
        stop_event=stop_event,
        injector=injector,
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
    )

    in_queue.put(
        CaptureCommand(
            session_id=1,
            keyword="alexa",
            action="inject_text",
            text="first",
            start_ts=1.0,
            end_ts=1.2,
        )
    )
    in_queue.put(
        CaptureCommand(
            session_id=2,
            keyword="alexa",
            action="inject_text",
            text="second",
            start_ts=1.2,
            end_ts=1.4,
        )
    )
    stop_event.set()

    worker._run()

    assert injector.texts == ["first", "second"]


def test_injector_worker_start_is_idempotent(monkeypatch):
    starts: list[tuple[object, object, object]] = []

    class FakeThread:
        def __init__(self, target, name, daemon):  # type: ignore[no-untyped-def]
            starts.append((target, name, daemon))

        def start(self) -> None:
            return

        def join(self, timeout: float | None = None) -> None:
            _ = timeout

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(threading, "Thread", FakeThread)
    worker = InjectorWorker(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        injector=FakeInjector(),
        openclaw_command=("openclaw", "agent", "--message", "{text}"),
        openclaw_timeout_s=20.0,
    )

    worker.start()
    worker.start()

    assert len(starts) == 1
