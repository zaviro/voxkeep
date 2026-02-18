# 本地常驻语音转写 + 唤醒截取 + 文本注入（MVP）设计文档

**日期：** 2026-02-16
**状态：** 已确认
**目标平台：** Ubuntu 24.04

## 1. 目标与边界

### 1.1 目标
- 实现单条音频流的持续 ASR（FunASR streaming）与长期落库（SQLite）。
- 实现唤醒后截取“下一句完整人声”的短线逻辑，并向当前焦点应用注入文本。
- ASR 不因唤醒启停；存储不等待唤醒。

### 1.2 非目标
- 当前阶段不接入 LLM。
- 不创建 GUI。

## 2. 硬约束

1. 全项目仅 `audio_capture` 可打开/管理 `sounddevice`。
2. `sounddevice` 回调仅 copy + enqueue，禁止重计算/IO/网络。
3. 预处理只执行一次，输出 fan-out 给 wake/vad/asr。
4. 必须具备抽象边界：`AudioSource`、`ASREngine`、`Injector`。
5. 所有参数来自 `config.yaml` 或环境变量。
6. SQLite 仅允许 `storage_worker` 持有连接并写入。
7. `capture_fsm` 采用四态：`IDLE -> ARMED -> CAPTURING -> FINALIZING -> IDLE`。
8. `Ctrl+C` 统一优雅退出，可立即重启。

## 3. 运行环境检查基线（当前机器实测）

- `echo $XDG_SESSION_TYPE` => `x11`
- `pactl list short sources` => 当前仅发现 `hdmi-stereo.monitor`（需切换到物理麦克风）
- `python3 -c "import sounddevice"` => `ModuleNotFoundError`（需安装依赖）
- FunASR `127.0.0.1:10096` TCP 探活 => `ConnectionRefusedError`（服务未启动或端口未配置）
- `xdotool` 已存在

## 4. 架构与数据流

长线（持续记录）：
`AudioSource -> Preprocess(once) -> ASR streaming -> ASR final event -> storage_worker(SQLite)`

短线（唤醒截取一句）：
`AudioSource -> Preprocess(once) -> wake + vad + asr_final_bus -> capture_fsm -> injector + storage_worker`

模块：
- `audio_capture` + `audio_bus`
- `wake_worker` / `vad_worker` / `asr_worker`
- `asr_event_bus`
- `capture_fsm`
- `storage_worker`
- `injector`
- `shutdown` 协调

## 5. capture_fsm 规则

- `IDLE`：等待 wake。
- `ARMED`：wake 后等待下一次 `speech_start`。
- `CAPTURING`：记录该句起止窗口，收集窗口内 ASR final。
- `FINALIZING`：拼接文本并注入一次，随后回 `IDLE`。

鲁棒性：
- `CAPTURING` 期间连续 wake 忽略或仅刷新内部标记，不允许二次注入。
- 对误唤醒支持超时回退到 `IDLE`。

## 6. 注入策略

- X11：`xdotool type --clearmodifiers --delay 1 <text>`
- Wayland：`ydotool type ...`
- Wayland 权限失败降级：输出可操作提示（`ydotoold`/`uinput`），并仅打印待注入文本。
- 注入后行为：**不自动回车**（已确认）。

## 7. MVP 验收

1. 连续说话 N 分钟后，SQLite 中 final 记录随时间增长且带时间戳。
2. 唤醒词 + 一句话：仅该句在结束后注入当前焦点输入框，且只注入一次。
3. `Ctrl+C` 退出后可立刻重启，不占用麦克风、不锁 DB。
4. 无唤醒时 ASR 仍持续写 `stream` final。
