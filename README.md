# VoxKeep

[![CI](https://github.com/zaviro/voxkeep/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zaviro/voxkeep/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

本项目在 Ubuntu 24.04 上实现本地常驻语音链路：持续 ASR、唤醒后截取一句、并注入当前焦点输入框。

## 5 分钟跑起来

```bash
make sync-ai
make setup-ai-models
make doctor
make validate-config
make run
```

对应的 CLI 入口：

```bash
python -m voxkeep doctor
python -m voxkeep config validate --config config/config.yaml
python -m voxkeep run --config config/config.yaml
```

说明：
- `doctor` 检查音频、FunASR、wake/vad 依赖和注入工具是否就绪。
- `config validate` 在启动前校验 YAML 配置与环境变量覆盖后的结果。
- `run` 启动本地常驻链路；旧的 `python -m voxkeep --config ...` 调用方式仍然兼容。

## 常用命令

```bash
make doctor
make validate-config
make run
make cli-check
make test
make lint
make typecheck
```

等价 CLI：

```bash
python -m voxkeep doctor
python -m voxkeep config validate --config config/config.yaml
python -m voxkeep check
python -m voxkeep run --config config/config.yaml
```

## 项目结构

```text
src/
  voxkeep/
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
VOXKEEP_WAKE_MODEL=hey_jarvis make setup-ai-models
```

## 运行

推荐先执行：

```bash
make doctor
make validate-config
```

```bash
make run
```

默认行为：
- `scripts/run_local.sh` 会通过 `docker compose up -d funasr` 管理 ASR 服务生命周期；
- 然后在本机 Python 进程中启动 `voxkeep`；
- 退出时默认会 `stop funasr`（可通过环境变量关闭）。

常用环境变量：
- `VOXKEEP_FUNASR_IMAGE`：FunASR Docker 镜像（默认 `gpudokerasr`）。
- `VOXKEEP_MANAGE_FUNASR=0`：不管理 ASR 容器，连接外部已运行的 FunASR。
- `VOXKEEP_FUNASR_DOCKER_SERVICE`：compose 中的 ASR service 名称（默认 `funasr`）。
- `VOXKEEP_FUNASR_STOP_ON_EXIT=0`：应用退出时不停止 ASR 容器。

等价命令：

```bash
uv run --python 3.11 python -m voxkeep run --config config/config.yaml
```

仅启动 Docker ASR 服务（本机运行 VoxKeep）：

```bash
VOXKEEP_FUNASR_IMAGE=gpudokerasr docker compose up -d funasr
make run
```

全容器运行（ASR + VoxKeep）：

```bash
VOXKEEP_FUNASR_IMAGE=gpudokerasr docker compose up -d funasr voxkeep
```

完整 wake/vad + ONNX + 注入链路运行：

```bash
make run-ai
```

## 测试与质量检查

```bash
make cli-check
make test
make lint
make typecheck
make test-cov
make precommit
```

说明：
- `make cli-check` 顺序执行 `ruff check`、`pyright`、`pytest -q`，适合本地提交前快速自检。
- `make typecheck` 通过 `pyright` 做静态类型检查，并已作为 CI 阻塞门禁。
- `make test-cov` 输出终端覆盖率摘要并生成 `coverage.xml`。

### GPT-SoVITS E2E 夹具规范

- `tests/e2e/test_pipeline_tts_audio.py` 只读取固定夹具音频，不会在测试时调用 TTS。
- 默认容器 API 可通过 `~/workspace/gptsovits/scripts/start_api_cuda.sh` 启动。
- 首次或需要更新夹具时，执行：

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh
```

- 仅运行 GPT-SoVITS 夹具 E2E：

```bash
VOXKEEP_RUN_GPTSOVITS_E2E=1 uv run --python 3.11 python -m pytest tests/e2e/test_pipeline_tts_audio.py -q
```

- 运行真实 OpenClaw 集成测试：

```bash
VOXKEEP_RUN_OPENCLAW_REAL=1 uv run --python 3.11 python -m pytest tests/integration/test_openclaw_real_call.py -q
```

- 运行带真实 OpenClaw 的 GPT-SoVITS E2E：

```bash
VOXKEEP_RUN_GPTSOVITS_E2E=1 VOXKEEP_RUN_OPENCLAW_REAL=1 uv run --python 3.11 python -m pytest tests/e2e/test_pipeline_tts_audio.py -q
```

检查 runtime-ai 可用性：

```bash
make check-ai
```

## 运行前检查

```bash
make doctor
```

仍可直接运行底层脚本：

```bash
scripts/check_env.sh
```

首次启用 pre-commit：

```bash
uv run --python 3.11 pre-commit install
```

## 说明

- 唤醒词检测默认使用 openwakeword 的 ONNX 推理框架。
- 默认唤醒模型为 `alexa`，可通过 `VOXKEEP_WAKE_MODEL` 覆盖。
- 默认帧长 `frame_ms=32`（512 samples@16k），与 silero-vad 默认输入长度对齐。
- 注入策略：X11 使用 `xdotool`，Wayland 使用 `ydotool`。
- 数据落库：仅 `storage_worker` 写 SQLite。
- 当前阶段不接入 LLM，不提供 GUI。
- Docker 默认基于 Python 3.11，已包含 runtime-ai 依赖与注入工具。
