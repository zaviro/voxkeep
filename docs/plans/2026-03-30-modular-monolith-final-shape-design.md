# ASR-OL 模块化单体最终形态收口设计

**日期：** 2026-03-30
**状态：** 已确认
**目标：** 将当前已完成主边界切换的仓库继续收口到最终形态，使 `shared / modules / bootstrap` 成为唯一真实架构层，`core / infra / services` 不再承载运行实现。

## 1. 问题陈述

当前仓库已经完成以下关键转向：

- 组合根已迁入 `bootstrap/`
- 顶层业务模块已建立：`capture / transcription / injection / storage / runtime`
- 大部分旧兼容 wrapper 已删除
- 模块公开 API 和架构测试已经建立

但仍存在三类未收口问题：

1. `shared/` 仍在转发 `core/`
2. `bootstrap/` 仍直接依赖 `core / infra / services`
3. `audio / wake / vad` 仍留在旧技术分层下

因此，当前状态是“模块化单体主骨架已就位”，但不是最终形态。

## 2. 收口目标

本轮完成后应满足以下条件：

- `shared/` 提供真实的配置、事件、接口与日志/队列工具
- `bootstrap/` 只依赖 `shared/` 与 `modules/*`
- `audio_capture / audio_bus / preprocess` 下沉到 `modules/runtime`
- `wake / vad` 下沉到 `modules/capture`
- `core / infra / services` 目录不再承载任何生产实现

## 3. 目标结构

```text
src/asr_ol/
  bootstrap/
    runtime_app.py
    shutdown.py
  modules/
    runtime/
      infrastructure/
        audio_bus.py
        audio_capture.py
        lifecycle.py
        preprocess.py
    capture/
      infrastructure/
        openwakeword_worker.py
        silero_worker.py
  shared/
    config.py
    events.py
    interfaces.py
    logging_setup.py
    queue_utils.py
```

## 4. 设计决策

### 4.1 `shared/` 直接承接 `core/`

将以下内容直接迁入 `shared/`：

- `core.config` -> `shared.config`
- `core.events` -> `shared.events`
- `core.queue_utils` -> `shared.queue_utils`
- `core.logging_setup` -> `shared.logging_setup`
- `core.asr_engine` 与 `core.audio_source` -> `shared.interfaces`

`shared.types` 保留，但不再承担历史事件兼容职责。

### 4.2 `runtime` 模块拥有音频输入与总线

运行时模块负责音频输入与 fanout 管线，因此收拢：

- `infra.audio.audio_capture`
- `infra.audio.preprocess`
- `services.audio_bus`
- `services.lifecycle`

它们属于运行时编排基础设施，而不是独立业务模块。

### 4.3 `capture` 模块拥有 wake/vad 输入适配器

`wake` 与 `vad` 的职责是把音频帧转成捕获相关事件，天然属于 `capture` 模块输入侧基础设施，因此收拢：

- `infra.vad.silero_worker`
- `infra.wake.openwakeword_worker`

### 4.4 `bootstrap` 只做装配与信号处理

`bootstrap` 最终只承担：

- 读取配置
- 装配模块
- 安装信号处理
- 启停运行时

信号处理从 `services.shutdown` 迁入 `bootstrap.shutdown`。

## 5. 架构规则

新增并强化以下规则：

- `shared` 不得 import `core / infra / services / modules`
- `bootstrap` 不得 import `core / infra / services`
- `modules/*` 不得 import `core / infra / services`
- `tests` 应优先引用新路径，不再依赖旧层

## 6. 风险与缓解

### 风险 1：全量 import 改写导致行为漂移

缓解：

- 先补架构测试再改实现
- 保持类名与行为不变，只迁移归属路径

### 风险 2：`runtime` 与 `capture` 模块边界重新耦合

缓解：

- `runtime` 只拥有音频输入与 fanout
- `capture` 只拥有 wake/vad 与捕获聚合
- 两者仍通过队列协作，不共享内部状态

### 风险 3：删除旧层后测试残留断裂

缓解：

- 优先改测试导入
- 删除旧层前先确认仓库内部无引用

## 7. 完成标准

满足以下条件时，认为仓库进入最终形态：

- 生产代码不再 import `asr_ol.core.*`
- 生产代码不再 import `asr_ol.infra.*`
- 生产代码不再 import `asr_ol.services.*`
- `bootstrap` 只依赖 `shared` 与 `modules`
- 旧层目录被删除或仅剩空包位于历史提交中，不再出现在当前树
