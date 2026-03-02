from __future__ import annotations

from dataclasses import replace
import threading

import pytest

from asr_ol.core.config import AppConfig
from asr_ol.services.runtime_app import AppRuntime


class _CallRecorder:
    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls
        self._alive = False

    def start(self) -> None:
        self._alive = True
        self._calls.append(f"start:{self._name}")

    def join(self, timeout: float | None = None) -> None:
        self._alive = False
        self._calls.append(f"join:{self._name}:{timeout}")

    def is_alive(self) -> bool:
        return self._alive


class _AudioSourceRecorder(_CallRecorder):
    def stop(self) -> None:
        self._calls.append(f"stop:{self._name}")


class _AudioSourceFailure(_AudioSourceRecorder):
    def stop(self) -> None:
        self._calls.append(f"stop:{self._name}")
        raise RuntimeError("boom")


class _FakeInjector:
    def inject(self, text: str) -> bool:
        _ = text
        return True


def test_runtime_builds_worker_lifecycle_plan(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr("asr_ol.services.runtime_app.build_injector", lambda _cfg: _FakeInjector())

    runtime = AppRuntime(app_config)

    startup_names = [item.name for item in runtime._startup_workers]
    shutdown_names = [item.name for item in runtime._shutdown_workers]

    assert startup_names == [
        "storage_worker",
        "capture_worker",
        "injector_worker",
        "wake_worker",
        "vad_worker",
        "asr_worker",
        "audio_bus",
    ]
    assert shutdown_names == [
        "audio_bus",
        "wake_worker",
        "vad_worker",
        "asr_worker",
        "capture_worker",
        "injector_worker",
        "storage_worker",
    ]


def test_runtime_start_and_stop_call_components_in_order():
    calls: list[str] = []
    runtime = AppRuntime.__new__(AppRuntime)
    runtime.stop_event = threading.Event()
    runtime.storage_worker = _CallRecorder("storage_worker", calls)
    runtime.capture_worker = _CallRecorder("capture_worker", calls)
    runtime.injector_worker = _CallRecorder("injector_worker", calls)
    runtime.wake_worker = _CallRecorder("wake_worker", calls)
    runtime.vad_worker = _CallRecorder("vad_worker", calls)
    runtime.asr_worker = _CallRecorder("asr_worker", calls)
    runtime.audio_bus = _CallRecorder("audio_bus", calls)
    runtime.audio_source = _AudioSourceRecorder("audio_source", calls)

    runtime._startup_workers = (
        runtime._worker_handle("storage_worker", runtime.storage_worker, 2),
        runtime._worker_handle("capture_worker", runtime.capture_worker, 2),
        runtime._worker_handle("injector_worker", runtime.injector_worker, 2),
        runtime._worker_handle("wake_worker", runtime.wake_worker, 2),
        runtime._worker_handle("vad_worker", runtime.vad_worker, 2),
        runtime._worker_handle("asr_worker", runtime.asr_worker, 3),
        runtime._worker_handle("audio_bus", runtime.audio_bus, 2),
    )
    runtime._shutdown_workers = (
        runtime._worker_handle("audio_bus", runtime.audio_bus, 2),
        runtime._worker_handle("wake_worker", runtime.wake_worker, 2),
        runtime._worker_handle("vad_worker", runtime.vad_worker, 2),
        runtime._worker_handle("asr_worker", runtime.asr_worker, 3),
        runtime._worker_handle("capture_worker", runtime.capture_worker, 2),
        runtime._worker_handle("injector_worker", runtime.injector_worker, 2),
        runtime._worker_handle("storage_worker", runtime.storage_worker, 2),
    )

    runtime.start()
    runtime.stop()

    assert runtime.stop_event.is_set() is True
    assert calls == [
        "start:storage_worker",
        "start:capture_worker",
        "start:injector_worker",
        "start:wake_worker",
        "start:vad_worker",
        "start:asr_worker",
        "start:audio_bus",
        "start:audio_source",
        "stop:audio_source",
        "join:audio_bus:2",
        "join:wake_worker:2",
        "join:vad_worker:2",
        "join:asr_worker:3",
        "join:capture_worker:2",
        "join:injector_worker:2",
        "join:storage_worker:2",
    ]


def test_runtime_stop_continues_when_audio_source_stop_fails():
    calls: list[str] = []
    runtime = AppRuntime.__new__(AppRuntime)
    runtime.stop_event = threading.Event()
    runtime.storage_worker = _CallRecorder("storage_worker", calls)
    runtime.capture_worker = _CallRecorder("capture_worker", calls)
    runtime.injector_worker = _CallRecorder("injector_worker", calls)
    runtime.wake_worker = _CallRecorder("wake_worker", calls)
    runtime.vad_worker = _CallRecorder("vad_worker", calls)
    runtime.asr_worker = _CallRecorder("asr_worker", calls)
    runtime.audio_bus = _CallRecorder("audio_bus", calls)
    runtime.audio_source = _AudioSourceFailure("audio_source", calls)
    runtime._shutdown_workers = (
        runtime._worker_handle("audio_bus", runtime.audio_bus, 2),
        runtime._worker_handle("wake_worker", runtime.wake_worker, 2),
        runtime._worker_handle("vad_worker", runtime.vad_worker, 2),
        runtime._worker_handle("asr_worker", runtime.asr_worker, 3),
        runtime._worker_handle("capture_worker", runtime.capture_worker, 2),
        runtime._worker_handle("injector_worker", runtime.injector_worker, 2),
        runtime._worker_handle("storage_worker", runtime.storage_worker, 2),
    )

    runtime.stop()

    assert runtime.stop_event.is_set() is True
    assert calls[0] == "stop:audio_source"
    assert calls[-1] == "join:storage_worker:2"


def test_runtime_init_wires_asr_and_capture_queues(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr("asr_ol.services.runtime_app.build_injector", lambda _cfg: _FakeInjector())
    cfg = replace(app_config, max_queue_size=8)

    runtime = AppRuntime(cfg)

    assert runtime.asr_worker._in_queue is runtime.asr_audio_queue
    assert runtime.asr_worker._final_in_queue is runtime.asr_engine.final_queue
    assert runtime.capture_worker._asr_queue is runtime.capture_asr_queue
    assert runtime.storage_worker._in_queue is runtime.storage_queue
    assert runtime.raw_queue.maxsize == 8


def test_run_forever_raises_when_worker_is_unhealthy():
    calls: list[str] = []
    runtime = AppRuntime.__new__(AppRuntime)
    runtime.stop_event = threading.Event()
    worker = _CallRecorder("asr_worker", calls)
    runtime._startup_workers = (runtime._worker_handle("asr_worker", worker, 1),)

    with pytest.raises(RuntimeError, match="asr_worker"):
        runtime.run_forever()
