# 本地常驻语音转写 + 唤醒截取 + 文本注入 设计文档

**日期：** 2026-02-15
**状态：** 已确认
**目标系统：** Ubuntu 24.04（当前会话类型：`x11`）

## 1. 目标与边界

### 1.1 目标
- 单条麦克风输入流持续采集与转写（16kHz/mono/PCM）。
- 持续写入长期存储（SQLite，按需并行写 JSONL）。
- 唤醒后执行句子级截取：`回溯最近2秒 + wake后直到静音800ms`。
- 截取文本完成后注入当前焦点输入框（X11 用 `xdotool`）。
- `Ctrl+C` 优雅退出，资源可立即重启复用。

### 1.2 非目标
- 本阶段不接入 LLM。
- 不实现 GUI 窗口。
- 不实现远程多机部署。

## 2. 约束与已确认输入

- FunASR WebSocket 地址：`ws://127.0.0.1:10096`（已确认）。
- 音频采集：`sounddevice`。
- 唤醒词：`openWakeWord`。
- VAD：优先 `Silero VAD`。
- 存储：SQLite（可选 JSONL）。
- 注入策略：
  - `x11`：`xdotool`
  - `wayland`：`ydotool`（权限策略后置）

## 3. 方案对比（已评估）

### 方案A：单进程多线程 + 队列扇出（推荐）
- 优点：实现快、依赖简单、易排障，适配 MVP。
- 风险：线程间背压处理要明确。
- 结论：采用。

### 方案B：单进程 asyncio 主导
- 优点：WebSocket 与调度统一。
- 风险：音频回调与阻塞库桥接复杂，调试成本更高。

### 方案C：多进程解耦（采集/识别/存储分进程）
- 优点：隔离性强、可扩展。
- 风险：IPC 与部署复杂度高，超出当前 MVP。

## 4. 模块架构

### 4.1 线程与队列
- `audio_callback`（sounddevice内部线程）
  - 仅做 `bytes(frame)` 与 `q_audio_in.put_nowait(...)`
  - 禁止任何重计算与 IO（含 DB、网络、日志落盘）
- `fanout_worker`
  - 消费 `q_audio_in`
  - 维护 2 秒环形缓冲（用于 wake 回溯）
  - 扇出到：
    - `q_wake_audio`
    - `q_vad_audio`
    - `q_asr_audio`
- `wake_worker`
  - openWakeWord 推理，产出 `WakeDetected`
- `vad_worker`
  - Silero VAD 推理，产出 `SpeechStart` / `SpeechEndCandidate`
- `asr_ws_worker`
  - 与 FunASR 通信，产出 `AsrPartial` / `AsrFinal`
- `capture_controller`
  - 状态机聚合 wake/vad/asr 事件，产出 `CaptureFinalText`
- `storage_worker`
  - 仅写 final（ASR final 与 capture final），落 SQLite/JSONL
- `injector_worker`
  - 消费 `CaptureFinalText`，向当前焦点输入框注入

### 4.2 状态机（capture）
- `IDLE`
  - 收到 `WakeDetected` -> `ARMED`
- `ARMED`
  - 把 ring buffer 最近 2 秒加入当前 capture 缓冲
  - 首次检测到语音 -> `CAPTURING`
- `CAPTURING`
  - 累积语音片段与 ASR final 片段
  - 检测到连续静音 >= 800ms -> `FINALIZING`
- `FINALIZING`
  - 生成一句文本并发给 `storage_worker` 与 `injector_worker`
  - 清空上下文 -> `IDLE`

## 5. 数据与存储

### 5.1 SQLite 表（MVP）
- 表：`asr_final_segments`
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `source TEXT NOT NULL` (`stream` / `capture`)
  - `text TEXT NOT NULL`
  - `start_ts REAL`
  - `end_ts REAL`
  - `created_at TEXT NOT NULL`（ISO 8601）
  - `meta_json TEXT`（可选扩展）

### 5.2 写入原则
- 只写 final，不写 partial。
- SQLite 写入放在独立 worker。
- 主流程通过队列投递，避免阻塞实时链路。

## 6. 注入策略

- `x11`：执行 `xdotool type --clearmodifiers --delay 1 "<text>"`
- `wayland`：
  - 首选 `ydotool type ...`
  - 若权限不足（需要 `ydotoold` 或 uinput 组权限），记录错误并降级为仅存储不注入
- 禁止创建新 GUI；只向当前焦点应用注入。

## 7. 失败处理与可观测性

- 队列溢出：计数+告警日志，丢弃最旧或当前块（配置化，MVP 默认丢当前块并计数）。
- ASR 断链：指数退避重连（1s/2s/4s，上限30s）。
- Wake/VAD 模型异常：模块降级并打印诊断，不影响主进程退出流程。
- 全局日志分级：`INFO` 默认，`DEBUG` 可选。

## 8. 优雅退出

1. 捕获 `SIGINT` -> 设置 `stop_event`
2. 停止音频输入流并 `close()`
3. 通知 ASR worker 发送 websocket close frame
4. drain 队列并完成 storage flush
5. 关闭 SQLite 连接
6. join 所有 worker（超时保护）
7. 退出码 0

## 9. 里程碑与可运行验证

### 里程碑 M1：音频链路打通（采集->扇出）
- 验证：启动后打印设备名、采样率、队列吞吐计数；连续运行 3 分钟无崩溃。

### 里程碑 M2：ASR final 落库
- 验证：说 3 句话，`sqlite3` 查询能看到 3+ 条 `stream` final。

### 里程碑 M3：wake 截取一句
- 验证：说“唤醒词 + 一句话”，能生成一条 `capture` final，文本接近完整句子。

### 里程碑 M4：焦点注入
- 验证：在终端或编辑器焦点处，唤醒并说一句，文本自动输入且不弹新窗口。

### 里程碑 M5：优雅退出
- 验证：`Ctrl+C` 后 2 秒内退出；立刻重启无“设备占用/数据库锁死”。
