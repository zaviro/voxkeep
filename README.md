# asr-ol

本项目在 Ubuntu 24.04 上实现本地常驻语音链路：持续 ASR、唤醒后截取一句、并注入当前焦点输入框。

## 项目结构

```text
src/
  asr_ol/
    __main__.py
    core/
    services/
    api/
    infra/
    agents/
    tools/
    cli/
tests/
  unit/
  integration/
  e2e/
```

## 环境与依赖（uv）

项目运行时锁定 Python 3.11。

1. 同步开发依赖（3.11）：

```bash
make sync
```

2. 安装 wake/vad 运行时依赖（3.11）：

```bash
make sync-ai
```

3. 预下载并验证 openwakeword ONNX 模型资源：

```bash
make setup-ai-models
```

可选：通过环境变量切换唤醒模型（默认 `alexa`）：

```bash
ASR_OL_WAKE_MODEL=hey_jarvis make setup-ai-models
```

## 运行

```bash
make run
```

等价命令：

```bash
uv run --python 3.11 python -m asr_ol --config config/config.yaml
```

完整 wake/vad + ONNX + 注入链路运行：

```bash
make run-ai
```

## 测试与质量检查

```bash
make test
make lint
make precommit
```

检查 runtime-ai 可用性：

```bash
make check-ai
```

## 运行前检查

```bash
scripts/check_env.sh
```

首次启用 pre-commit：

```bash
uv run --python 3.11 pre-commit install
```

## 说明

- 唤醒词检测默认使用 openwakeword 的 ONNX 推理框架。
- 默认唤醒模型为 `alexa`，可通过 `ASR_OL_WAKE_MODEL` 覆盖。
- 默认帧长 `frame_ms=32`（512 samples@16k），与 silero-vad 默认输入长度对齐。
- 注入策略：X11 使用 `xdotool`，Wayland 使用 `ydotool`。
- 数据落库：仅 `storage_worker` 写 SQLite。
- 当前阶段不接入 LLM，不提供 GUI。
- Docker 默认基于 Python 3.11，已包含 runtime-ai 依赖与注入工具。
