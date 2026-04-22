# VoxKeep

[![CI](https://github.com/zaviro/voxkeep/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zaviro/voxkeep/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`VoxKeep` 是一个面向 Linux 桌面的本地常驻语音链路：持续监听麦克风音频，检测唤醒词，用 VAD + ASR 截取一句完整语音，然后把最终文本注入当前焦点输入框，或分发到 `openclaw agent` 这类动作。

## 当前状态

- 运行时代码已经迁移到模块化单体结构：`src/voxkeep/modules/*`、`src/voxkeep/bootstrap/`、`src/voxkeep/shared/`。
- 仓库内提交的 `config/config.yaml` 当前默认选择 `qwen_vllm` 外部服务，目标地址是 `ws://127.0.0.1:8000/v1/realtime`。
- `VoxKeep` 不负责启动或停止 Qwen `vLLM` 服务；Qwen 服务应由仓库外部独立管理。
- 如果你要严格按 `config/config.yaml` 内容运行，请直接使用 CLI 或 `make run`。

## 快速开始

### 开发环境

```bash
make sync
make test-fast
make lint
make typecheck
```

### 按当前 `qwen_vllm` 配置运行

1. 在仓库外部先启动本地 Qwen `vLLM` ASR 服务。
2. 准备运行时依赖和唤醒模型：

```bash
make sync-ai
make setup-ai-models
```

3. 做环境和配置检查：

```bash
make doctor
make validate-config
uv run --python 3.11 python -m voxkeep backend current --config config/config.yaml
uv run --python 3.11 python -m voxkeep backend doctor --config config/config.yaml
```

4. 直接运行 VoxKeep：

```bash
make run
```

说明：

- `make doctor` 负责检查会话类型、音频源、wake/VAD 依赖、注入工具和当前配置对应的 WebSocket ASR 健康状态。
- `backend current` 用来确认配置最终解析出的后端。
- `backend doctor` 会输出当前后端的健康分类；如果资产状态缺失或服务不可用，会非零退出。

## CLI 概览

```bash
uv run --python 3.11 python -m voxkeep --help
```

主要子命令：

- `run`: 启动本地运行时。
- `doctor`: 运行环境诊断脚本。
- `check`: 顺序执行 `ruff check`、`pyright`、`pytest -q`。
- `config validate --config <path>`: 校验配置文件和 `VOXKEEP_*` 环境变量覆盖后的结果。
- `backend list`: 列出内建 ASR 后端。
- `backend current --config <path>`: 显示当前配置解析后的 ASR 后端。
- `backend doctor --config <path>`: 检查当前配置的 ASR 后端健康状态。
- `asset status <backend_id>`: 查看某个后端的已安装资源状态；`backend doctor` 会依赖这份状态。

## 项目结构

```text
src/voxkeep/
  bootstrap/      # 顶层运行时装配与生命周期
  modules/
    capture/      # 唤醒词、VAD、句子截取状态机
    transcription/ # ASR 后端适配与转写入口
    injection/    # 文本注入与动作执行
    storage/      # SQLite 持久化
    audio_engine/  # 音频采集、预处理、audio bus
  shared/         # 配置、事件、日志、队列工具
  api/            # 外部 API 入口
  cli/            # CLI 入口
tests/
  unit/
  integration/
  e2e/
  architecture/
```

`src/voxkeep/core/`、`src/voxkeep/infra/`、`src/voxkeep/services/` 仍存在，但属于退役命名空间；不要再向这些目录新增运行时代码。

## 配置速览

当前主要配置文件是 `config/config.yaml`。重点字段：

- `asr.backend`: 当前仅支持 `qwen_vllm`。
- `asr.mode`: `external`。
- `asr.external.*`: 当前活动 WebSocket ASR 服务的地址。
- `asr.runtime.*`: ASR 连接重试参数。
- `asr.qwen.*`: Qwen `vLLM` 相关参数。
- `wake.rules`: 唤醒词到动作的路由规则。
- `injector.backend`: `auto`、`xdotool`、`ydotool`。
- `actions.openclaw_agent`: `openclaw agent` 的命令模板和超时。

## 常用命令

```bash
make sync
make sync-ai
make setup-ai-models
make check-ai
make doctor
make validate-config
make cli-check
make test-fast
make test-unit
make test-architecture
make test-integration
make test-e2e
make test
make test-cov
make lint
make fmt
make typecheck
make precommit
```

## 测试分层

- `tests/unit` + `tests/architecture`: 默认高频反馈回路，适合日常开发。
- `tests/integration`: 改动 worker、生命周期、runtime wiring、模块协作时再跑。
- `tests/e2e`: 低频验收；涉及真实外部服务、桌面注入、GPT-SoVITS 夹具或完整运行链路时使用。

## GPT-SoVITS 夹具 E2E

- `tests/e2e/test_pipeline_tts_audio.py` 只使用预生成音频夹具，不会在测试时调用 TTS。
- 夹具目录：`tests/fixtures/audio/gptsovits/`
- 重新生成夹具：

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

## 说明

- 唤醒词检测使用 `openwakeword`，VAD 使用 `silero-vad`。
- 默认采样率是 `16kHz`，默认帧长是 `32ms`。
- 注入后端 `auto` 会按桌面会话自动选择：X11 用 `xdotool`，Wayland 用 `ydotool`。
- SQLite 只允许由 storage 模块写入。
- 当前阶段不提供 GUI，也不在运行时链路内直接接入通用 LLM。
