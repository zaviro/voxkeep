from __future__ import annotations

from dataclasses import replace
import threading

import pytest

from voxkeep.bootstrap.runtime_app import AppRuntime
from voxkeep.shared.config import AppConfig
from voxkeep.modules.capture.public import CaptureModule
from voxkeep.modules.injection.public import InjectionModule
from voxkeep.modules.storage.public import StorageModule
from voxkeep.modules.transcription.public import TranscriptionModule


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
    def start(self) -> None:
        self._calls.append(f"start:{self._name}")
        raise RuntimeError("boom")

    def stop(self) -> None:
        self._calls.append(f"stop:{self._name}")
        raise RuntimeError("boom")


class _FakeInjector:
    def inject(self, text: str) -> bool:
        _ = text
        return True


class _FakeWorker:
    def start(self) -> None:
        return

    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return True


class _FakeStorageModule(StorageModule):
    def __init__(self) -> None:
        self._in_queue = object()

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return True

    def store_transcript(self, event):  # type: ignore[no-untyped-def]
        return event

    def store_capture(self, event):  # type: ignore[no-untyped-def]
        return event


class _FakeInjectionModule(InjectionModule):
    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return True

    def execute_capture(self, event):  # type: ignore[no-untyped-def]
        return event


class _FakeCaptureModule(CaptureModule):
    def __init__(self) -> None:
        self._wake_queue = object()
        self._vad_queue = object()
        self._asr_queue = object()

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def accept_wake(self, event):  # type: ignore[no-untyped-def]
        return

    def accept_vad(self, event):  # type: ignore[no-untyped-def]
        return

    def accept_transcript(self, event):  # type: ignore[no-untyped-def]
        return

    def subscribe_capture_completed(self, handler):  # type: ignore[no-untyped-def]
        _ = handler

    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return True


class _FakeTranscriptionModule(TranscriptionModule):
    def __init__(self) -> None:
        self._in_queue = object()
        self._final_in_queue = object()
        self._engine = type("FakeEngine", (), {"final_queue": object()})()

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def submit_audio(self, frame):  # type: ignore[no-untyped-def]
        return

    def subscribe_transcript_finalized(self, handler):  # type: ignore[no-untyped-def]
        _ = handler

    def join(self, timeout: float | None = None) -> None:
        _ = timeout

    def is_alive(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _patch_runtime_ai_worker_builders(monkeypatch) -> None:
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_detection_workers",
        lambda **_kwargs: (_FakeWorker(), _FakeWorker()),
    )


def test_runtime_builds_worker_lifecycle_plan(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module",
        lambda **_kwargs: _FakeCaptureModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module",
        lambda **_kwargs: _FakeStorageModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: _FakeTranscriptionModule(),
    )

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


def test_runtime_builds_runtime_ai_workers_through_builder_functions(
    monkeypatch,
    app_config: AppConfig,
):
    fake_wake_worker = _FakeWorker()
    fake_vad_worker = _FakeWorker()
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module",
        lambda **_kwargs: _FakeCaptureModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module",
        lambda **_kwargs: _FakeStorageModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: _FakeTranscriptionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_detection_workers",
        lambda **_kwargs: (fake_wake_worker, fake_vad_worker),
        raising=False,
    )

    runtime = AppRuntime(app_config)

    assert runtime.wake_worker is fake_wake_worker
    assert runtime.vad_worker is fake_vad_worker


def test_runtime_does_not_expose_transcription_private_engine(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module",
        lambda **_kwargs: _FakeCaptureModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module",
        lambda **_kwargs: _FakeStorageModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: _FakeTranscriptionModule(),
    )

    runtime = AppRuntime(app_config)

    assert not hasattr(runtime, "asr_engine")


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
    fake_capture = _FakeCaptureModule()
    fake_transcription = _FakeTranscriptionModule()
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module", lambda **_kwargs: fake_capture
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: fake_transcription,
    )
    fake_storage = _FakeStorageModule()
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module", lambda **_kwargs: fake_storage
    )
    cfg = replace(app_config, max_queue_size=8)

    runtime = AppRuntime(cfg)

    assert runtime.asr_worker is fake_transcription
    assert runtime.capture_worker is fake_capture
    assert runtime.storage_worker is fake_storage
    assert runtime.raw_queue.maxsize == 8


def test_runtime_builds_storage_through_module_public_api(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module",
        lambda **_kwargs: _FakeCaptureModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: _FakeTranscriptionModule(),
    )
    built: dict[str, object] = {}

    def _build_storage_module(**kwargs):  # type: ignore[no-untyped-def]
        built.update(kwargs)
        return _FakeStorageModule()

    monkeypatch.setattr("voxkeep.bootstrap.runtime_app.build_storage_module", _build_storage_module)

    runtime = AppRuntime(app_config)

    assert runtime.storage_worker is not None
    assert built["in_queue"] is runtime.storage_queue
    assert built["stop_event"] is runtime.stop_event
    assert built["cfg"] is app_config


def test_runtime_builds_injection_through_module_public_api(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module",
        lambda **_kwargs: _FakeCaptureModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: _FakeTranscriptionModule(),
    )
    fake_storage = _FakeStorageModule()
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module", lambda **_kwargs: fake_storage
    )
    built: dict[str, object] = {}

    def _build_injection_module(**kwargs):  # type: ignore[no-untyped-def]
        built.update(kwargs)
        return _FakeInjectionModule()

    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module", _build_injection_module
    )

    runtime = AppRuntime(app_config)

    assert runtime.injector_worker is not None
    assert built["in_queue"] is runtime.capture_cmd_queue
    assert built["stop_event"] is runtime.stop_event
    assert built["cfg"] is app_config


def test_runtime_builds_capture_through_module_public_api(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        lambda **_kwargs: _FakeTranscriptionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module",
        lambda **_kwargs: _FakeStorageModule(),
    )
    built: dict[str, object] = {}

    def _build_capture_module(**kwargs):  # type: ignore[no-untyped-def]
        built.update(kwargs)
        return _FakeCaptureModule()

    monkeypatch.setattr("voxkeep.bootstrap.runtime_app.build_capture_module", _build_capture_module)

    runtime = AppRuntime(app_config)

    assert runtime.capture_worker is not None
    assert built["wake_queue"] is runtime.wake_event_queue
    assert built["vad_queue"] is runtime.vad_event_queue
    assert built["asr_queue"] is runtime.capture_asr_queue
    assert built["downstream_queue"] is runtime.capture_cmd_queue
    assert built["storage_queue"] is runtime.storage_queue


def test_runtime_builds_transcription_through_module_public_api(monkeypatch, app_config: AppConfig):
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_capture_module",
        lambda **_kwargs: _FakeCaptureModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_injection_module",
        lambda **_kwargs: _FakeInjectionModule(),
    )
    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_storage_module",
        lambda **_kwargs: _FakeStorageModule(),
    )
    built: dict[str, object] = {}

    def _build_transcription_module(**kwargs):  # type: ignore[no-untyped-def]
        built.update(kwargs)
        return _FakeTranscriptionModule()

    monkeypatch.setattr(
        "voxkeep.bootstrap.runtime_app.build_transcription_module",
        _build_transcription_module,
    )

    runtime = AppRuntime(app_config)

    assert runtime.asr_worker is not None
    assert built["in_queue"] is runtime.asr_audio_queue
    assert built["capture_queue"] is runtime.capture_asr_queue
    assert built["storage_queue"] is runtime.storage_queue
    assert built["stop_event"] is runtime.stop_event
    assert built["cfg"] is app_config


def test_run_forever_raises_when_worker_is_unhealthy():
    calls: list[str] = []
    runtime = AppRuntime.__new__(AppRuntime)
    runtime.stop_event = threading.Event()
    runtime._fatal_error = None
    worker = _CallRecorder("asr_worker", calls)
    runtime._startup_workers = (runtime._worker_handle("asr_worker", worker, 1),)

    runtime.run_forever()

    assert runtime.stop_event.is_set() is True
    assert runtime.fatal_error == "worker stopped unexpectedly: asr_worker"


def test_find_unhealthy_workers_returns_all_dead_workers():
    runtime = AppRuntime.__new__(AppRuntime)
    runtime._startup_workers = (
        runtime._worker_handle("wake_worker", _CallRecorder("wake_worker", []), 1),
        runtime._worker_handle("vad_worker", _CallRecorder("vad_worker", []), 1),
    )

    assert runtime._find_unhealthy_workers() == ("wake_worker", "vad_worker")


def test_run_forever_exits_cleanly_when_stop_event_already_set():
    runtime = AppRuntime.__new__(AppRuntime)
    runtime.stop_event = threading.Event()
    runtime.stop_event.set()
    runtime._fatal_error = None
    runtime._startup_workers = ()

    runtime.run_forever()

    assert runtime.fatal_error is None


def test_start_propagates_audio_source_start_failure():
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
    runtime._startup_workers = (
        runtime._worker_handle("storage_worker", runtime.storage_worker, 2),
        runtime._worker_handle("capture_worker", runtime.capture_worker, 2),
        runtime._worker_handle("injector_worker", runtime.injector_worker, 2),
        runtime._worker_handle("wake_worker", runtime.wake_worker, 2),
        runtime._worker_handle("vad_worker", runtime.vad_worker, 2),
        runtime._worker_handle("asr_worker", runtime.asr_worker, 3),
        runtime._worker_handle("audio_bus", runtime.audio_bus, 2),
    )

    with pytest.raises(RuntimeError, match="boom"):
        runtime.start()

    assert calls[-1] == "start:audio_source"
