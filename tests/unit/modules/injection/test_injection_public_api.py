from __future__ import annotations

import queue
import threading

from asr_ol.modules.injection.contracts import InjectionResult
from asr_ol.modules.injection.public import build_injection_module
from asr_ol.shared.config import AppConfig
from asr_ol.shared.types import CaptureCompleted


def test_injection_module_executes_capture_completed(monkeypatch, app_config: AppConfig) -> None:
    monkeypatch.setattr(
        "asr_ol.modules.injection.public.build_injector",
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
