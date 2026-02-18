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

1. 同步开发依赖：

```bash
make sync
```

2. 如需 wake/vad 运行时依赖：

```bash
make sync-ai
```

说明：`openwakeword` 在 Python 3.12 下不可用，`make sync-ai` 会自动切换到 Python 3.11 环境。

## 运行

```bash
make run
```

等价命令：

```bash
uv run python -m asr_ol --config config/config.yaml
```

启用 wake/vad 运行时依赖后，建议用 3.11 profile 运行：

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
uv run pre-commit install
```

## 说明

- 注入策略：X11 使用 `xdotool`，Wayland 使用 `ydotool`。
- 数据落库：仅 `storage_worker` 写 SQLite。
- 当前阶段不接入 LLM，不提供 GUI。
- Docker 默认基于 Python 3.11，已包含 runtime-ai 依赖与注入工具。
