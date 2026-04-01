from __future__ import annotations

from dataclasses import replace
import queue
import sys
import types

import numpy as np
import pytest

from voxkeep.shared.config import AppConfig
from voxkeep.modules.runtime.infrastructure.audio_capture import SoundDeviceAudioSource


def test_callback_only_enqueues_audio_chunk(app_config: AppConfig):
    out = queue.Queue(maxsize=2)
    cfg = replace(app_config, max_queue_size=2)
    src = SoundDeviceAudioSource(out_queue=out, cfg=cfg)

    frame = np.zeros((320, 1), dtype=np.int16)
    src._on_audio(frame, 320, None, None)

    item = out.get_nowait()
    assert item.frames == 320
    assert isinstance(item.data, bytes)


def test_callback_drops_when_queue_full(app_config: AppConfig):
    out = queue.Queue(maxsize=1)
    cfg = replace(app_config, max_queue_size=1)
    src = SoundDeviceAudioSource(out_queue=out, cfg=cfg)

    frame = np.zeros((320, 1), dtype=np.int16)
    src._on_audio(frame, 320, None, None)
    src._on_audio(frame, 320, None, None)

    assert src.dropped_chunks == 1


def test_audio_source_start_builds_input_stream_with_expected_config(
    app_config: AppConfig, monkeypatch
):
    calls: dict[str, object] = {}

    class FakeStream:
        def start(self) -> None:
            calls["started"] = True

        def stop(self) -> None:
            calls["stopped"] = True

        def close(self) -> None:
            calls["closed"] = True

    def fake_input_stream(**kwargs):  # type: ignore[no-untyped-def]
        calls.update(kwargs)
        return FakeStream()

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.InputStream = fake_input_stream  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    src = SoundDeviceAudioSource(out_queue=queue.Queue(), cfg=app_config)

    src.start()

    assert calls["samplerate"] == app_config.sample_rate
    assert calls["channels"] == app_config.channels
    assert calls["blocksize"] == app_config.frame_samples
    assert calls["dtype"] == "int16"
    assert callable(calls["callback"])
    assert calls["started"] is True


def test_audio_source_start_is_idempotent(app_config: AppConfig, monkeypatch):
    starts = 0

    class FakeStream:
        def start(self) -> None:
            nonlocal starts
            starts += 1

        def stop(self) -> None:
            return

        def close(self) -> None:
            return

    fake_sd = types.ModuleType("sounddevice")
    fake_sd.InputStream = lambda **kwargs: FakeStream()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    src = SoundDeviceAudioSource(out_queue=queue.Queue(), cfg=app_config)

    src.start()
    src.start()

    assert starts == 1


def test_audio_source_stop_is_idempotent(app_config: AppConfig) -> None:
    src = SoundDeviceAudioSource(out_queue=queue.Queue(), cfg=app_config)

    src.stop()
    src.stop()


def test_audio_source_stop_calls_stream_stop_and_close(app_config: AppConfig) -> None:
    calls: list[str] = []

    class FakeStream:
        def stop(self) -> None:
            calls.append("stop")

        def close(self) -> None:
            calls.append("close")

    src = SoundDeviceAudioSource(out_queue=queue.Queue(), cfg=app_config)
    src._stream = FakeStream()

    src.stop()

    assert calls == ["stop", "close"]


def test_audio_source_start_raises_runtime_error_when_sounddevice_missing(
    app_config: AppConfig, monkeypatch
) -> None:
    monkeypatch.delitem(sys.modules, "sounddevice", raising=False)
    original_import = __import__

    def fake_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "sounddevice":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    src = SoundDeviceAudioSource(out_queue=queue.Queue(), cfg=app_config)

    with pytest.raises(RuntimeError, match="sounddevice is required"):
        src.start()
