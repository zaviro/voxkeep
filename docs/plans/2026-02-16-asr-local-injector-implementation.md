# ASR Local Injector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local daemon that continuously performs ASR, stores timestamped final segments, captures one post-wake sentence, and injects only that sentence into the focused input field.

**Architecture:** A single `sounddevice` input callback enqueues raw audio only. A single preprocessor produces normalized frames once, then fans out to wake/VAD/ASR workers. `capture_fsm` consumes wake+VAD+ASR-final events to produce one-shot capture text. `storage_worker` exclusively writes SQLite records. `injector` chooses X11/Wayland backend by session type.

**Tech Stack:** Python 3.12, sounddevice, openWakeWord, silero-vad, websockets, sqlite3, threading, queue, pytest.

---

### Task 1: 项目骨架与依赖清单

**Files:**
- Create: `pyproject.toml`
- Create: `src/asr_ol/__init__.py`
- Create: `src/asr_ol/main.py`
- Create: `tests/test_smoke_import.py`

**Step 1: 写失败测试**

```python
# tests/test_smoke_import.py

def test_import_main_module():
    import asr_ol.main  # noqa: F401
```

**Step 2: 验证失败**
- Run: `pytest tests/test_smoke_import.py -v`
- Expected: `ModuleNotFoundError: No module named 'asr_ol'`

**Step 3: 最小实现**

```toml
# pyproject.toml
[project]
name = "asr-ol"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "PyYAML>=6.0.1",
  "numpy>=1.26.4",
  "websockets>=12.0",
  "sounddevice>=0.4.6",
  "openwakeword>=0.6.0",
  "silero-vad>=5.1.2"
]

[project.optional-dependencies]
dev = ["pytest>=8.2.0"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```python
# src/asr_ol/__init__.py
__all__ = ["main"]
```

```python
# src/asr_ol/main.py

def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: 验证通过**
- Run: `pytest tests/test_smoke_import.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add pyproject.toml src/asr_ol/__init__.py src/asr_ol/main.py tests/test_smoke_import.py`
- Run: `git commit -m "chore: bootstrap asr-ol skeleton"`

### Task 2: 配置系统（YAML + 环境变量覆盖）

**Files:**
- Create: `config/config.yaml`
- Create: `src/asr_ol/config.py`
- Create: `tests/test_config.py`

**Step 1: 写失败测试**

```python
# tests/test_config.py
from asr_ol.config import AppConfig, load_config


def test_load_config_from_yaml_and_env(tmp_path, monkeypatch):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text("sample_rate: 16000\nframe_ms: 20\nfunasr:\n  host: 127.0.0.1\n  port: 10096\n")
    monkeypatch.setenv("ASR_OL_PRE_ROLL_MS", "1500")
    cfg = load_config(str(cfg_file))
    assert isinstance(cfg, AppConfig)
    assert cfg.sample_rate == 16000
    assert cfg.frame_ms == 20
    assert cfg.pre_roll_ms == 1500
```

**Step 2: 验证失败**
- Run: `pytest tests/test_config.py -v`
- Expected: import error

**Step 3: 最小实现**
- `config/config.yaml` 写入所有默认项（host/port/path/sample_rate/frame_ms/silence/pre_roll/injector/jsonl_debug）。
- `src/asr_ol/config.py` 提供：
  - `@dataclass AppConfig`
  - `load_config(path: str) -> AppConfig`
  - `ASR_OL_` 前缀环境变量覆盖

**Step 4: 验证通过**
- Run: `pytest tests/test_config.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add config/config.yaml src/asr_ol/config.py tests/test_config.py`
- Run: `git commit -m "feat: add yaml and env based config"`

### Task 3: 事件模型与抽象边界

**Files:**
- Create: `src/asr_ol/events.py`
- Create: `src/asr_ol/audio/source.py`
- Create: `src/asr_ol/asr/base.py`
- Create: `src/asr_ol/injector/base.py`
- Create: `tests/test_boundaries.py`

**Step 1: 写失败测试**
- 断言 `AudioSource`、`ASREngine`、`Injector` 为抽象接口。
- 断言核心事件 dataclass 字段齐全。

**Step 2: 验证失败**
- Run: `pytest tests/test_boundaries.py -v`
- Expected: import error

**Step 3: 最小实现**
- `events.py`：`RawAudioChunk`、`ProcessedFrame`、`WakeEvent`、`VadEvent`、`AsrFinalEvent`、`StorageRecord`、`CaptureCommand`。
- `audio/source.py`：`AudioSource.start()/stop()`。
- `asr/base.py`：`ASREngine.start()/submit_frame()/close()`。
- `injector/base.py`：`Injector.inject(text)`。

**Step 4: 验证通过**
- Run: `pytest tests/test_boundaries.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/events.py src/asr_ol/audio/source.py src/asr_ol/asr/base.py src/asr_ol/injector/base.py tests/test_boundaries.py`
- Run: `git commit -m "feat: add event models and core abstractions"`

### Task 4: 单流采集与轻量回调

**Files:**
- Create: `src/asr_ol/audio/audio_capture.py`
- Create: `tests/test_audio_capture.py`

**Step 1: 写失败测试**
- 直接调用 callback，断言仅向队列写入 `RawAudioChunk`。
- 队列满时只递增 drop 计数，不抛异常。

**Step 2: 验证失败**
- Run: `pytest tests/test_audio_capture.py -v`
- Expected: import error

**Step 3: 最小实现**
- `SoundDeviceAudioSource(AudioSource)`：
  - `start()` 打开 `sounddevice.InputStream`
  - callback 内仅 `indata.copy().tobytes()` + `put_nowait`
  - `stop()` 关闭 stream

**Step 4: 验证通过**
- Run: `pytest tests/test_audio_capture.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/audio/audio_capture.py tests/test_audio_capture.py`
- Run: `git commit -m "feat: add single stream capture with enqueue-only callback"`

### Task 5: 预处理与 fan-out（只处理一次）

**Files:**
- Create: `src/asr_ol/audio/preprocess.py`
- Create: `src/asr_ol/audio/audio_bus.py`
- Create: `tests/test_audio_bus.py`

**Step 1: 写失败测试**
- 输入一条 `RawAudioChunk`，验证 `wake/vad/asr` 三队列都收到同一个 `ProcessedFrame`（按 frame index 可校验）。
- 验证预处理函数调用次数为 1 次。

**Step 2: 验证失败**
- Run: `pytest tests/test_audio_bus.py -v`
- Expected: import error

**Step 3: 最小实现**
- `Preprocessor.process(chunk) -> ProcessedFrame`
- `AudioBus.run_once()`：从 raw 队列取数据，预处理一次后 fan-out 到三个消费者队列。

**Step 4: 验证通过**
- Run: `pytest tests/test_audio_bus.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/audio/preprocess.py src/asr_ol/audio/audio_bus.py tests/test_audio_bus.py`
- Run: `git commit -m "feat: add preprocess once and audio fanout bus"`

### Task 6: `capture_fsm` 四态 + 单次注入

**Files:**
- Create: `src/asr_ol/capture/fsm.py`
- Create: `tests/test_capture_fsm.py`

**Step 1: 写失败测试**
- 覆盖路径：`IDLE -> ARMED -> CAPTURING -> FINALIZING -> IDLE`。
- 验证 wake 后一句语音只产生一次 `CaptureCommand`。
- 验证连续 wake 不会重复注入。

**Step 2: 验证失败**
- Run: `pytest tests/test_capture_fsm.py -v`
- Expected: import error

**Step 3: 最小实现**
- 显式状态枚举与转换函数。
- 维护 `current_session_id`、`injected_once`、`speech_window`。
- `finalize()` 只在本次会话输出一次命令。

**Step 4: 验证通过**
- Run: `pytest tests/test_capture_fsm.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/capture/fsm.py tests/test_capture_fsm.py`
- Run: `git commit -m "feat: add wake capture state machine with one-shot injection"`

### Task 7: `storage_worker`（SQLite 独占写入）

**Files:**
- Create: `src/asr_ol/storage/worker.py`
- Create: `tests/test_storage_worker.py`

**Step 1: 写失败测试**
- 推送 2 条 `StorageRecord`，断言 SQLite 中写入成功且带时间戳。
- 验证 worker 停止时连接关闭。

**Step 2: 验证失败**
- Run: `pytest tests/test_storage_worker.py -v`
- Expected: import error

**Step 3: 最小实现**
- `StorageWorker` 线程独占连接。
- 表结构 `asr_segments`（`source/text/start_ts/end_ts/is_final/created_at/meta_json`）。
- 可选 JSONL 调试输出开关。

**Step 4: 验证通过**
- Run: `pytest tests/test_storage_worker.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/storage/worker.py tests/test_storage_worker.py`
- Run: `git commit -m "feat: add sqlite storage worker and final segment persistence"`

### Task 8: 注入后端（xdotool/ydotool）与降级

**Files:**
- Create: `src/asr_ol/injector/xdotool_injector.py`
- Create: `src/asr_ol/injector/ydotool_injector.py`
- Create: `src/asr_ol/injector/factory.py`
- Create: `tests/test_injector.py`

**Step 1: 写失败测试**
- Mock `subprocess.run`，断言 X11 下执行 `xdotool type --clearmodifiers --delay 1`。
- Wayland 注入失败时返回 False 并包含提示信息。

**Step 2: 验证失败**
- Run: `pytest tests/test_injector.py -v`
- Expected: import error

**Step 3: 最小实现**
- `XdotoolInjector.inject(text)`。
- `YdotoolInjector.inject(text)`，失败时打印 `ydotoold/uinput` 提示。
- `build_injector(session_type, mode)`。

**Step 4: 验证通过**
- Run: `pytest tests/test_injector.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/injector/xdotool_injector.py src/asr_ol/injector/ydotool_injector.py src/asr_ol/injector/factory.py tests/test_injector.py`
- Run: `git commit -m "feat: add x11/wayland injector with fallback hints"`

### Task 9: Wake/VAD Worker 框架（可替换实现）

**Files:**
- Create: `src/asr_ol/wake/openwakeword_worker.py`
- Create: `src/asr_ol/vad/silero_worker.py`
- Create: `tests/test_wake_vad_workers.py`

**Step 1: 写失败测试**
- 用 fake predictor/fake vad，输入 `ProcessedFrame`，断言可产出事件对象。

**Step 2: 验证失败**
- Run: `pytest tests/test_wake_vad_workers.py -v`
- Expected: import error

**Step 3: 最小实现**
- worker 只消费队列并发出事件；不访问声卡。
- 实现可注入 predictor，便于无模型单测。

**Step 4: 验证通过**
- Run: `pytest tests/test_wake_vad_workers.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/wake/openwakeword_worker.py src/asr_ol/vad/silero_worker.py tests/test_wake_vad_workers.py`
- Run: `git commit -m "feat: add wake and vad worker scaffolding"`

### Task 10: FunASR WebSocket 引擎与重连

**Files:**
- Create: `src/asr_ol/asr/funasr_ws.py`
- Create: `tests/test_funasr_ws.py`

**Step 1: 写失败测试**
- mock websocket 客户端，断言：
  - 能发送音频帧
  - 收到 final 时发出 `AsrFinalEvent`
  - 断链时按指数退避重连

**Step 2: 验证失败**
- Run: `pytest tests/test_funasr_ws.py -v`
- Expected: import error

**Step 3: 最小实现**
- `FunAsrWsEngine(ASREngine)`：后台线程 + asyncio loop。
- 输入音频队列、输出 final 事件队列。
- 重连策略 `1s/2s/4s...max30s`。

**Step 4: 验证通过**
- Run: `pytest tests/test_funasr_ws.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/asr/funasr_ws.py tests/test_funasr_ws.py`
- Run: `git commit -m "feat: add funasr websocket engine with reconnect backoff"`

### Task 11: 运行时编排与统一关闭

**Files:**
- Create: `src/asr_ol/runtime/app.py`
- Create: `src/asr_ol/runtime/shutdown.py`
- Modify: `src/asr_ol/main.py`
- Create: `tests/test_shutdown.py`

**Step 1: 写失败测试**
- 构造 fake workers，触发 shutdown，断言 stop 顺序与 join 被调用。

**Step 2: 验证失败**
- Run: `pytest tests/test_shutdown.py -v`
- Expected: import error

**Step 3: 最小实现**
- `AppRuntime.start()/run()/stop()`。
- 捕获 `SIGINT` 设置 `shutdown_event`。
- 关闭顺序：audio -> asr ws -> workers drain -> sqlite close -> join。

**Step 4: 验证通过**
- Run: `pytest tests/test_shutdown.py -v`
- Expected: PASS

**Step 5: 提交**
- Run: `git add src/asr_ol/runtime/app.py src/asr_ol/runtime/shutdown.py src/asr_ol/main.py tests/test_shutdown.py`
- Run: `git commit -m "feat: add runtime orchestration and graceful shutdown"`

### Task 12: 端到端冒烟脚本与验收手册

**Files:**
- Create: `scripts/check_env.sh`
- Create: `scripts/run_local.sh`
- Create: `docs/plans/2026-02-16-mvp-acceptance.md`

**Step 1: 写失败检查**
- 运行 `scripts/check_env.sh` 前期望报缺失项（如 sounddevice/FunASR）。

**Step 2: 编写脚本**
- `check_env.sh`：检查 session type、sources、xdotool/ydotool、FunASR 端口。
- `run_local.sh`：加载配置并启动主程序。

**Step 3: 验证脚本输出**
- Run: `bash scripts/check_env.sh`
- Expected: 明确 PASS/FAIL 与修复建议。

**Step 4: 编写验收文档**
- 写入 5 条 MVP 用例和命令、预期输出、排障路径。

**Step 5: 提交**
- Run: `git add scripts/check_env.sh scripts/run_local.sh docs/plans/2026-02-16-mvp-acceptance.md`
- Run: `git commit -m "docs: add env check scripts and mvp acceptance runbook"`

---

Plan complete and saved to `docs/plans/2026-02-16-asr-local-injector-implementation.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints
