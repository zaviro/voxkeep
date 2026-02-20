# ASR-OL 项目认知地图（第 1 步）

**日期：** 2026-02-20
**目的：** 先建立“从启动到数据落地”的整体心智模型，再进入细节调试与改动。

## 1. 启动入口（Call Chain）

1. `src/asr_ol/__main__.py` 进入 CLI 主流程。
2. `src/asr_ol/cli/main.py` 负责：
   - 解析 `--config`
   - 加载配置 `load_config`
   - 初始化日志
   - 创建 `AppRuntime`
   - 安装 `SIGINT/SIGTERM` 优雅退出
3. `src/asr_ol/services/runtime_app.py` 完成所有队列、worker、engine 的装配与生命周期管理。

## 2. 运行时装配（Runtime Composition）

`AppRuntime` 内部核心组件：

- 音频入口：`SoundDeviceAudioSource`
- 分发总线：`AudioBus`（单次预处理 + fan-out）
- 检测链路：`OpenWakeWordWorker` + `SileroVadWorker`
- ASR 链路：`FunAsrWsEngine` + `AsrWorker`
- 短线控制：`CaptureFSM` + `CaptureWorker`
- 输出执行：`InjectorWorker`（`xdotool`/`ydotool`）
- 持久化：`StorageWorker`（SQLite / 可选 JSONL）

## 3. 数据流（Data Flow）

### 3.1 长线（持续转写与存储）

`AudioSource -> AudioBus(Preprocess once) -> ASR -> AsrFinalEvent -> StorageWorker`

说明：
- `AudioBus` 只做一次 `Preprocessor.process`，结果同时送往 wake/vad/asr，避免重复计算。
- `AsrWorker` 将 final 事件写入 `storage_queue`（受 `store_final_only` 控制）。

### 3.2 短线（唤醒后一句注入）

`WakeEvent + VadEvent + AsrFinalEvent -> CaptureFSM -> CaptureCommand -> InjectorWorker`

FSM 状态：
- `IDLE -> ARMED -> CAPTURING -> FINALIZING -> IDLE`

关键规则：
- 唤醒后仅捕获“下一句完整语音”。
- 连续 wake 不会重复注入同一句。
- `speech_end` 到达后拼接窗口内 ASR final 并一次性注入。

## 4. 约束边界（Architecture Boundaries）

- 仅 `audio_capture` 打开麦克风（`sounddevice`）。
- `sounddevice` 回调仅 copy + enqueue，不做重计算/IO。
- 仅 `storage_worker` 持有 SQLite 连接并写库。
- 抽象边界保留在 `core`：
  - `AudioSource`
  - `ASREngine`
  - `Injector`

## 5. 配置与环境覆盖

配置来源优先级：
1. 代码默认值（`core/config.py`）
2. `config/config.yaml`
3. 环境变量 `ASR_OL_*`（最终覆盖）

常用项：
- 音频：`sample_rate`、`frame_ms`
- ASR：`funasr.host/port/path`
- 检测：`wake.threshold`、`vad.speech_threshold`
- 捕获：`capture.pre_roll_ms`、`capture.armed_timeout_ms`
- 注入：`injector.backend`、`injector.auto_enter`

## 6. 先读哪些文件（推荐顺序）

1. `src/asr_ol/cli/main.py`
2. `src/asr_ol/services/runtime_app.py`
3. `src/asr_ol/core/events.py`
4. `src/asr_ol/services/audio_bus.py`
5. `src/asr_ol/infra/asr/funasr_ws.py`
6. `src/asr_ol/services/asr_worker.py`
7. `src/asr_ol/agents/capture_fsm.py`
8. `src/asr_ol/agents/capture_worker.py`
9. `src/asr_ol/services/injector_worker.py`
10. `src/asr_ol/infra/storage/storage_worker.py`

## 7. 用测试反向理解（第 2 阶段入口）

- `tests/unit/agents/test_capture_fsm.py`：一句话捕获与防重复注入
- `tests/integration/test_audio_bus.py`：单次预处理 + 三路分发
- `tests/integration/test_wake_vad_workers.py`：wake/vad 事件触发行为
- `tests/unit/core/test_boundaries.py`：抽象边界与事件形状

## 8. 快速验证命令

```bash
make run
make test
scripts/check_env.sh
```
