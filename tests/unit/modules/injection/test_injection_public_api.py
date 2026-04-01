from __future__ import annotations

import queue
import threading

from voxkeep.modules.injection.contracts import InjectionResult
from voxkeep.modules.injection.public import build_injection_module
from voxkeep.shared.config import AppConfig
from voxkeep.shared.types import CaptureCompleted


def test_injection_module_executes_capture_completed(monkeypatch, app_config: AppConfig) -> None:
    monkeypatch.setattr(
        "voxkeep.modules.injection.public.build_injector",
        lambda _cfg: type("FakeInjector", (), {"inject": lambda self, text: text == "hello"})(),
    )
    module = build_injection_module(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        cfg=app_config,
    )

    result = module.execute_capture(
        CaptureCompleted(
            session_id=1,
            keyword="alexa",
            action="inject_text",
            text="hello",
            start_ts=1.0,
            end_ts=1.2,
        )
    )

    assert result == InjectionResult(ok=True, action="inject_text")


def test_injection_module_stop_sets_stop_event(monkeypatch, app_config: AppConfig) -> None:
    monkeypatch.setattr(
        "voxkeep.modules.injection.public.build_injector",
        lambda _cfg: type("FakeInjector", (), {"inject": lambda self, text: True})(),
    )
    stop_event = threading.Event()
    module = build_injection_module(
        in_queue=queue.Queue(),
        stop_event=stop_event,
        cfg=app_config,
    )

    module.stop()

    assert stop_event.is_set() is True


def test_injection_module_execute_capture_uses_public_worker_api(
    monkeypatch, app_config: AppConfig
) -> None:
    class _FakeWorker:
        def __init__(
            self,
            in_queue: queue.Queue[object],
            stop_event: threading.Event,
            injector: object,
            openclaw_command: tuple[str, ...],
            openclaw_timeout_s: float,
        ) -> None:
            _ = (in_queue, stop_event, injector, openclaw_command, openclaw_timeout_s)

        def start(self) -> None:
            return

        def join(self, timeout: float | None = None) -> None:
            _ = timeout

        def is_alive(self) -> bool:
            return True

        def execute_command(self, cmd):  # type: ignore[no-untyped-def]
            return cmd.action == "inject_text" and cmd.text == "hello"

    monkeypatch.setattr(
        "voxkeep.modules.injection.public.build_injector",
        lambda _cfg: type("FakeInjector", (), {"inject": lambda self, text: True})(),
    )
    monkeypatch.setattr("voxkeep.modules.injection.public.InjectorWorker", _FakeWorker)

    module = build_injection_module(
        in_queue=queue.Queue(),
        stop_event=threading.Event(),
        cfg=app_config,
    )

    result = module.execute_capture(
        CaptureCompleted(
            session_id=1,
            keyword="alexa",
            action="inject_text",
            text="hello",
            start_ts=1.0,
            end_ts=1.2,
        )
    )

    assert result == InjectionResult(ok=True, action="inject_text")
