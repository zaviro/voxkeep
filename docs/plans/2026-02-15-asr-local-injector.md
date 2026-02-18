# Local ASR Wake Capture Injector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local daemon on Ubuntu 24.04 that performs continuous ASR, persists timestamped final text, captures one sentence after wake word (`2s pre-roll + 800ms silence`), and injects it into the currently focused input field.

**Architecture:** Use a single microphone stream with a lightweight `sounddevice` callback that only enqueues audio chunks. Fan out queued chunks to wake word, VAD, and FunASR streaming workers; merge events in a capture state machine; persist final-only records via a dedicated SQLite worker; and inject capture text via session-aware injector (`x11 -> xdotool`, `wayland -> ydotool`).

**Tech Stack:** Python 3.11+, sounddevice, openWakeWord, Silero VAD, websockets, sqlite3, pytest.

---

### Task 1: Bootstrap Project + Runtime Config

**Files:**
- Create: `pyproject.toml`
- Create: `src/asr_ol/__init__.py`
- Create: `src/asr_ol/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_config.py
from asr_ol.config import AppConfig


def test_defaults_match_mvp():
    cfg = AppConfig()
    assert cfg.sample_rate == 16000
    assert cfg.channels == 1
    assert cfg.funasr_ws_url == "ws://127.0.0.1:10096"
    assert cfg.capture_preroll_ms == 2000
    assert cfg.capture_silence_ms == 800
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asr_ol'`

**Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "asr-ol"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "numpy>=1.26.0",
  "sounddevice>=0.4.6",
  "websockets>=12.0",
  "openwakeword>=0.6.0",
  "silero-vad>=5.1.2",
]

[project.optional-dependencies]
dev = ["pytest>=8.0.0"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```python
# src/asr_ol/__init__.py
__all__ = ["config"]
```

```python
# src/asr_ol/config.py
from dataclasses import dataclass


@dataclass(slots=True)
class AppConfig:
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 1600  # 100ms @16k
    funasr_ws_url: str = "ws://127.0.0.1:10096"
    capture_preroll_ms: int = 2000
    capture_silence_ms: int = 800
    sqlite_path: str = "data/asr.db"
    jsonl_path: str | None = "data/asr.jsonl"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml src/asr_ol/__init__.py src/asr_ol/config.py tests/test_config.py
git commit -m "chore: bootstrap project config for local asr mvp"
```

### Task 2: Define Event Models (Audio/Wake/VAD/ASR/Capture)

**Files:**
- Create: `src/asr_ol/events.py`
- Test: `tests/test_events.py`

**Step 1: Write the failing test**

```python
# tests/test_events.py
from asr_ol.events import AudioChunk, AsrFinal


def test_event_dataclasses_have_expected_fields():
    c = AudioChunk(data=b"abc", ts=1.23, frames=1600, sample_rate=16000)
    a = AsrFinal(text="hello", start_ts=1.0, end_ts=1.5, source="stream")
    assert c.frames == 1600
    assert a.source == "stream"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asr_ol.events'`

**Step 3: Write minimal implementation**

```python
# src/asr_ol/events.py
from dataclasses import dataclass


@dataclass(slots=True)
class AudioChunk:
    data: bytes
    ts: float
    frames: int
    sample_rate: int


@dataclass(slots=True)
class WakeDetected:
    ts: float
    score: float


@dataclass(slots=True)
class VadEvent:
    ts: float
    is_speech: bool


@dataclass(slots=True)
class AsrFinal:
    text: str
    start_ts: float
    end_ts: float
    source: str  # stream | capture


@dataclass(slots=True)
class CaptureFinal:
    text: str
    start_ts: float
    end_ts: float
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_events.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/events.py tests/test_events.py
git commit -m "feat: add core event dataclasses"
```

### Task 3: Single Mic Stream Callback (Enqueue-Only)

**Files:**
- Create: `src/asr_ol/audio_capture.py`
- Test: `tests/test_audio_capture.py`

**Step 1: Write the failing test**

```python
# tests/test_audio_capture.py
import queue
import numpy as np

from asr_ol.audio_capture import AudioInput


def test_callback_only_enqueues_audio_chunk():
    q = queue.Queue(maxsize=1)
    ai = AudioInput(out_queue=q, sample_rate=16000, channels=1, block_size=1600)
    frame = np.zeros((1600, 1), dtype=np.int16)
    ai._callback(frame, 1600, None, None)
    item = q.get_nowait()
    assert item.frames == 1600
    assert isinstance(item.data, bytes)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asr_ol.audio_capture'`

**Step 3: Write minimal implementation**

```python
# src/asr_ol/audio_capture.py
from __future__ import annotations

import queue
import time

import sounddevice as sd

from .events import AudioChunk


class AudioInput:
    def __init__(self, out_queue: queue.Queue, sample_rate: int, channels: int, block_size: int):
        self.out_queue = out_queue
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self._stream: sd.InputStream | None = None
        self.dropped_chunks = 0

    # callback must stay lightweight: no heavy compute, no disk/network I/O
    def _callback(self, indata, frames, _time_info, _status):
        chunk = AudioChunk(
            data=indata.copy().tobytes(),
            ts=time.time(),
            frames=frames,
            sample_rate=self.sample_rate,
        )
        try:
            self.out_queue.put_nowait(chunk)
        except queue.Full:
            self.dropped_chunks += 1

    def start(self):
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.block_size,
            callback=self._callback,
            dtype="int16",
        )
        self._stream.start()

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio_capture.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/audio_capture.py tests/test_audio_capture.py
git commit -m "feat: add single-stream audio input with enqueue-only callback"
```

### Task 4: Fan-Out Worker + 2s Ring Buffer

**Files:**
- Create: `src/asr_ol/ring_buffer.py`
- Create: `src/asr_ol/fanout.py`
- Test: `tests/test_fanout.py`

**Step 1: Write the failing test**

```python
# tests/test_fanout.py
import queue
import time
from asr_ol.events import AudioChunk
from asr_ol.ring_buffer import AudioRingBuffer
from asr_ol.fanout import fanout_once


def test_fanout_copies_chunk_to_three_queues_and_ring():
    q_in = queue.Queue()
    q_w = queue.Queue()
    q_v = queue.Queue()
    q_a = queue.Queue()
    ring = AudioRingBuffer(max_seconds=2.0, sample_rate=16000, bytes_per_sample=2)
    c = AudioChunk(data=b"x" * 3200, ts=time.time(), frames=1600, sample_rate=16000)
    q_in.put(c)
    fanout_once(q_in, q_w, q_v, q_a, ring)
    assert q_w.get_nowait().frames == 1600
    assert q_v.get_nowait().frames == 1600
    assert q_a.get_nowait().frames == 1600
    assert len(ring.get_recent()) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_fanout.py -v`
Expected: FAIL with import errors

**Step 3: Write minimal implementation**

```python
# src/asr_ol/ring_buffer.py
from collections import deque

from .events import AudioChunk


class AudioRingBuffer:
    def __init__(self, max_seconds: float, sample_rate: int, bytes_per_sample: int):
        max_frames = int(max_seconds * sample_rate)
        self._max_frames = max_frames
        self._frames = 0
        self._chunks: deque[AudioChunk] = deque()
        self._bytes_per_frame = bytes_per_sample

    def append(self, chunk: AudioChunk):
        self._chunks.append(chunk)
        self._frames += chunk.frames
        while self._frames > self._max_frames and self._chunks:
            old = self._chunks.popleft()
            self._frames -= old.frames

    def get_recent(self) -> list[AudioChunk]:
        return list(self._chunks)
```

```python
# src/asr_ol/fanout.py
import queue

from .events import AudioChunk
from .ring_buffer import AudioRingBuffer


def fanout_once(
    q_in: queue.Queue,
    q_wake: queue.Queue,
    q_vad: queue.Queue,
    q_asr: queue.Queue,
    ring: AudioRingBuffer,
):
    chunk: AudioChunk = q_in.get(timeout=0.2)
    ring.append(chunk)
    q_wake.put_nowait(chunk)
    q_vad.put_nowait(chunk)
    q_asr.put_nowait(chunk)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_fanout.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/ring_buffer.py src/asr_ol/fanout.py tests/test_fanout.py
git commit -m "feat: add fanout worker primitive and preroll ring buffer"
```

### Task 5: Capture State Machine (Wake -> Speech -> Silence End)

**Files:**
- Create: `src/asr_ol/capture.py`
- Test: `tests/test_capture.py`

**Step 1: Write the failing test**

```python
# tests/test_capture.py
from asr_ol.capture import CaptureController
from asr_ol.events import AsrFinal


def test_capture_returns_sentence_after_silence():
    c = CaptureController(preroll_ms=2000, silence_ms=800)
    c.on_wake(10.0)
    c.on_vad(True, 10.1)
    c.on_asr_final(AsrFinal(text="你好世界", start_ts=10.2, end_ts=10.8, source="stream"))
    c.on_vad(False, 11.8)
    result = c.try_finalize(11.8)
    assert result is not None
    assert result.text == "你好世界"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_capture.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asr_ol.capture'`

**Step 3: Write minimal implementation**

```python
# src/asr_ol/capture.py
from collections import deque

from .events import AsrFinal, CaptureFinal


class CaptureController:
    def __init__(self, preroll_ms: int, silence_ms: int):
        self.preroll_sec = preroll_ms / 1000.0
        self.silence_sec = silence_ms / 1000.0
        self.state = "IDLE"
        self.capture_start_ts = 0.0
        self.last_speech_ts = 0.0
        self._final_history: deque[AsrFinal] = deque(maxlen=200)
        self._captured_texts: list[str] = []

    def on_wake(self, wake_ts: float):
        self.state = "ARMED"
        self.capture_start_ts = wake_ts - self.preroll_sec
        self.last_speech_ts = wake_ts
        self._captured_texts.clear()

    def on_vad(self, is_speech: bool, ts: float):
        if self.state == "IDLE":
            return
        if is_speech:
            self.state = "CAPTURING"
            self.last_speech_ts = ts

    def on_asr_final(self, ev: AsrFinal):
        self._final_history.append(ev)
        if self.state in {"ARMED", "CAPTURING"} and ev.end_ts >= self.capture_start_ts:
            self._captured_texts.append(ev.text)

    def try_finalize(self, now_ts: float) -> CaptureFinal | None:
        if self.state not in {"ARMED", "CAPTURING"}:
            return None
        if now_ts - self.last_speech_ts < self.silence_sec:
            return None
        text = "".join(self._captured_texts).strip()
        self.state = "IDLE"
        if not text:
            return None
        return CaptureFinal(text=text, start_ts=self.capture_start_ts, end_ts=now_ts)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_capture.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/capture.py tests/test_capture.py
git commit -m "feat: add wake-driven capture state machine"
```

### Task 6: SQLite Final-Only Storage Worker

**Files:**
- Create: `src/asr_ol/storage.py`
- Test: `tests/test_storage.py`

**Step 1: Write the failing test**

```python
# tests/test_storage.py
import queue
from asr_ol.events import AsrFinal
from asr_ol.storage import StorageWorker


def test_storage_inserts_final_rows(tmp_path):
    db_path = tmp_path / "asr.db"
    q = queue.Queue()
    w = StorageWorker(db_path=str(db_path), in_queue=q, jsonl_path=None)
    w.start()
    q.put(AsrFinal(text="test", start_ts=1.0, end_ts=1.2, source="stream"))
    q.put(None)
    w.join(timeout=3)
    assert w.inserted_count == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# src/asr_ol/storage.py
from __future__ import annotations

import json
import queue
import sqlite3
import threading
from datetime import datetime, timezone

from .events import AsrFinal, CaptureFinal


class StorageWorker(threading.Thread):
    def __init__(self, db_path: str, in_queue: queue.Queue, jsonl_path: str | None):
        super().__init__(daemon=True)
        self.db_path = db_path
        self.in_queue = in_queue
        self.jsonl_path = jsonl_path
        self.inserted_count = 0
        self._conn: sqlite3.Connection | None = None

    def _init_db(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asr_final_segments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              text TEXT NOT NULL,
              start_ts REAL,
              end_ts REAL,
              created_at TEXT NOT NULL,
              meta_json TEXT
            )
            """
        )
        self._conn.commit()

    def _insert(self, source: str, text: str, start_ts: float, end_ts: float):
        created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO asr_final_segments(source, text, start_ts, end_ts, created_at, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
            (source, text, start_ts, end_ts, created_at, "{}"),
        )
        self._conn.commit()
        self.inserted_count += 1
        if self.jsonl_path:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "source": source,
                            "text": text,
                            "start_ts": start_ts,
                            "end_ts": end_ts,
                            "created_at": created_at,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def run(self):
        self._init_db()
        while True:
            item = self.in_queue.get()
            if item is None:
                break
            if isinstance(item, AsrFinal):
                self._insert(item.source, item.text, item.start_ts, item.end_ts)
            elif isinstance(item, CaptureFinal):
                self._insert("capture", item.text, item.start_ts, item.end_ts)
        if self._conn:
            self._conn.close()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/storage.py tests/test_storage.py
git commit -m "feat: add sqlite storage worker for final-only records"
```

### Task 7: Session-Aware Text Injector (x11/wayland)

**Files:**
- Create: `src/asr_ol/injector.py`
- Test: `tests/test_injector.py`

**Step 1: Write the failing test**

```python
# tests/test_injector.py
from asr_ol.injector import build_inject_command


def test_x11_uses_xdotool():
    cmd = build_inject_command("x11", "hello")
    assert cmd[0] == "xdotool"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_injector.py -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# src/asr_ol/injector.py
from __future__ import annotations

import os
import subprocess


def build_inject_command(session_type: str, text: str) -> list[str]:
    if session_type == "x11":
        return ["xdotool", "type", "--clearmodifiers", "--delay", "1", text]
    if session_type == "wayland":
        return ["ydotool", "type", text]
    raise ValueError(f"Unsupported session_type: {session_type}")


class TextInjector:
    def __init__(self, session_type: str | None = None):
        self.session_type = session_type or os.getenv("XDG_SESSION_TYPE", "x11")

    def inject(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        cmd = build_inject_command(self.session_type, text)
        try:
            subprocess.run(cmd, check=True)
            return True
        except Exception:
            return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_injector.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/injector.py tests/test_injector.py
git commit -m "feat: add x11/wayland injector command strategy"
```

### Task 8: Wake + VAD Workers

**Files:**
- Create: `src/asr_ol/wake_worker.py`
- Create: `src/asr_ol/vad_worker.py`
- Test: `tests/test_wake_vad_workers.py`

**Step 1: Write the failing test**

```python
# tests/test_wake_vad_workers.py
from asr_ol.vad_worker import silence_elapsed


def test_silence_threshold():
    assert silence_elapsed(last_speech_ts=10.0, now_ts=10.81, threshold_ms=800)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_wake_vad_workers.py -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# src/asr_ol/wake_worker.py
from __future__ import annotations

from .events import AudioChunk, WakeDetected


class WakeDetector:
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self._model = None  # initialize openWakeWord model lazily in runtime task

    def detect(self, chunk: AudioChunk) -> WakeDetected | None:
        # Placeholder for model inference wiring; keep deterministic for tests.
        return None
```

```python
# src/asr_ol/vad_worker.py
from __future__ import annotations


def silence_elapsed(last_speech_ts: float, now_ts: float, threshold_ms: int) -> bool:
    return (now_ts - last_speech_ts) * 1000 >= threshold_ms
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_wake_vad_workers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/wake_worker.py src/asr_ol/vad_worker.py tests/test_wake_vad_workers.py
git commit -m "feat: add wake/vad worker skeletons and silence helper"
```

### Task 9: FunASR WebSocket Client

**Files:**
- Create: `src/asr_ol/funasr_client.py`
- Test: `tests/test_funasr_client.py`

**Step 1: Write the failing test**

```python
# tests/test_funasr_client.py
from asr_ol.funasr_client import parse_funasr_message


def test_parse_final_message():
    msg = {"text": "你好", "is_final": True, "start": 1.0, "end": 1.5}
    ev = parse_funasr_message(msg)
    assert ev is not None
    assert ev.text == "你好"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_funasr_client.py -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# src/asr_ol/funasr_client.py
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import websockets

from .events import AsrFinal


def parse_funasr_message(payload: dict) -> AsrFinal | None:
    if not payload.get("is_final"):
        return None
    return AsrFinal(
        text=str(payload.get("text", "")).strip(),
        start_ts=float(payload.get("start", 0.0)),
        end_ts=float(payload.get("end", 0.0)),
        source="stream",
    )


class FunASRClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url)

    async def send_audio(self, pcm_bytes: bytes):
        await self.ws.send(pcm_bytes)

    async def recv_loop(self, on_final: Callable[[AsrFinal], Awaitable[None]]):
        async for msg in self.ws:
            payload = json.loads(msg)
            ev = parse_funasr_message(payload)
            if ev:
                await on_final(ev)

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_funasr_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/funasr_client.py tests/test_funasr_client.py
git commit -m "feat: add minimal funasr websocket parser and client wrapper"
```

### Task 10: App Orchestration + Graceful Shutdown

**Files:**
- Create: `src/asr_ol/app.py`
- Create: `src/asr_ol/main.py`
- Test: `tests/test_app_shutdown.py`

**Step 1: Write the failing test**

```python
# tests/test_app_shutdown.py
import queue
from asr_ol.app import AppRuntime
from asr_ol.config import AppConfig


def test_shutdown_sets_stop_event():
    rt = AppRuntime(AppConfig())
    rt.shutdown()
    assert rt.stop_event.is_set()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_shutdown.py -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# src/asr_ol/app.py
from __future__ import annotations

import queue
import threading

from .audio_capture import AudioInput
from .config import AppConfig
from .injector import TextInjector


class AppRuntime:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.stop_event = threading.Event()
        self.q_audio_in: queue.Queue = queue.Queue(maxsize=128)
        self.audio = AudioInput(
            out_queue=self.q_audio_in,
            sample_rate=cfg.sample_rate,
            channels=cfg.channels,
            block_size=cfg.block_size,
        )
        self.injector = TextInjector()

    def start(self):
        self.audio.start()

    def shutdown(self):
        self.stop_event.set()
        self.audio.stop()
```

```python
# src/asr_ol/main.py
from __future__ import annotations

from .app import AppRuntime
from .config import AppConfig


def main():
    rt = AppRuntime(AppConfig())
    try:
        rt.start()
        while True:
            pass
    except KeyboardInterrupt:
        rt.shutdown()


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_app_shutdown.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/asr_ol/app.py src/asr_ol/main.py tests/test_app_shutdown.py
git commit -m "feat: add app runtime lifecycle and graceful shutdown baseline"
```

### Task 11: Runtime Check Script + Milestone Smoke Validation

**Files:**
- Create: `scripts/check_runtime.sh`
- Create: `README.md`

**Step 1: Write the failing test**

Create executable check script first, then validate by running it (shell script itself is verification artifact for this task).

**Step 2: Run check script and observe current failures**

Run: `bash scripts/check_runtime.sh`
Expected: If dependency/service missing, output explicit `*_FAIL` lines.

**Step 3: Write minimal implementation**

```bash
# scripts/check_runtime.sh
#!/usr/bin/env bash
set -euo pipefail

echo "== SESSION =="
echo "${XDG_SESSION_TYPE:-unknown}"

echo "== MIC DEVICES =="
python - <<'PY'
import sounddevice as sd
ok = False
for i,d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        ok = True
        print(f"{i}\t{d['name']}\tinputs={d['max_input_channels']}")
print("MIC_OK" if ok else "MIC_FAIL")
PY

echo "== FUNASR PORT =="
python - <<'PY'
import socket
try:
    socket.create_connection(("127.0.0.1",10096),2).close()
    print("FUNASR_PORT_OK")
except Exception as e:
    print("FUNASR_PORT_FAIL", e)
PY

echo "== FUNASR WS =="
python - <<'PY'
import asyncio, websockets
async def main():
    try:
        async with websockets.connect("ws://127.0.0.1:10096",open_timeout=3):
            print("FUNASR_WS_OK")
    except Exception as e:
        print("FUNASR_WS_FAIL", e)
asyncio.run(main())
PY
```

````markdown
# README.md

## Run

```bash
python -m pip install -e ".[dev]"
bash scripts/check_runtime.sh
python -m asr_ol.main
```

## Milestone Validation

1. M1 音频链路：日志出现连续音频块计数，3分钟稳定运行。
2. M2 持久化：`sqlite3 data/asr.db "select source,text from asr_final_segments order by id desc limit 5;"` 可见 `stream`。
3. M3 唤醒截取：说“唤醒词 + 一句话”，产生 `capture` 记录。
4. M4 文本注入：在当前焦点输入框看到自动输入。
5. M5 优雅退出：`Ctrl+C` 后可立即重启，无设备占用/数据库锁。
````

**Step 4: Run validation again**

Run: `bash scripts/check_runtime.sh`
Expected: 至少 `SESSION=x11`、`MIC_OK`；FunASR 未起时出现 `FUNASR_*_FAIL`（这是可诊断失败）。

**Step 5: Commit**

```bash
chmod +x scripts/check_runtime.sh
git add scripts/check_runtime.sh README.md
git commit -m "docs: add runtime checks and milestone smoke validation guide"
```

## Cross-Task Guardrails

- 永远只保留一个 `sounddevice.InputStream` 实例，禁止 wake/VAD/ASR 模块各自开麦。
- 音频回调函数只允许 `copy + put_nowait`，不得做模型推理、网络、磁盘 IO。
- SQLite 只在 `StorageWorker` 线程写入。
- capture 规则固定为：`2s preroll + 800ms silence`（配置可调）。
- 注入只打到当前焦点应用，禁止创建 GUI。
- 退出顺序固定：停止音频 -> 关闭WS -> flush存储 -> 关闭DB -> join线程。

## Milestone Commands (End-to-End)

```bash
# 1) 环境检查
bash scripts/check_runtime.sh

# 2) 启动服务端（示例，按你的 FunASR 部署方式）
# python your_funasr_server.py

# 3) 启动客户端
python -m asr_ol.main

# 4) 观察数据库
sqlite3 data/asr.db "select id,source,text,created_at from asr_final_segments order by id desc limit 20;"
```
