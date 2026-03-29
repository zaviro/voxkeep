# ASR-OL 模块化单体重构设计

**日期：** 2026-03-29
**状态：** 已确认
**目标：** 在保持 CLI、配置结构、单进程多线程运行语义不变的前提下，将当前分层单体重构为具备强模块边界的模块化单体。

## 1. 设计目标

### 1.1 必须保持不变

- CLI 启动方式保持不变：`python -m asr_ol --config ...`
- 配置来源与结构保持兼容：`config/config.yaml` 与 `ASR_OL_*`
- 运行模型保持不变：单进程、多线程、队列驱动
- 现有行为语义保持不变：持续 ASR、唤醒后单次注入、SQLite 单点写入、优雅退出

### 1.2 设计目标

- 按业务能力建立顶层模块边界，而不是继续以技术分层作为主边界
- 模块之间只能通过公开 API 协作，禁止跨模块穿透内部实现
- 组合根集中到 `bootstrap/`，统一装配各模块
- 架构约束进入测试与 CI，边界不再只靠约定维持

### 1.3 非目标

- 不拆分为多进程或微服务
- 不引入 GUI 或新的外部接口协议
- 不在本轮引入全局事件总线框架
- 不修改核心运行语义或产品行为

## 2. 现状判断

当前代码库已具备较强边界意识：

- 存在清晰的目录分层：`core / services / infra / agents / tools / api / cli`
- 存在抽象边界：`AudioSource`、`ASREngine`、`Injector`
- 存在单点资源约束：仅 `audio_capture` 打开麦克风，仅 `storage_worker` 写 SQLite
- 存在组合根雏形：`services/runtime_app.py`

但当前仍然不是严格模块化单体，主要问题为：

- 顶层边界仍以技术层划分，而不是业务模块
- 模块之间缺少机器可校验的依赖规则
- 内部实现默认可被跨层直接 import
- `core` 容易继续演变为全局共享中心层
- 架构测试只覆盖抽象存在，不覆盖越界依赖

## 3. 目标架构

### 3.1 顶层模块

重构后顶层业务模块固定为：

1. `transcription`
   - 负责持续 ASR、音频帧提交、最终转写结果产出
2. `capture`
   - 负责 wake + vad + transcript 聚合，形成“一句完整捕获”
3. `injection`
   - 负责注入文本与执行外部动作
4. `storage`
   - 负责流式转写与 capture 结果的持久化
5. `runtime`
   - 负责模块编排、生命周期、状态与运行时协调

### 3.2 共享层

保留最小 `shared/`，只放稳定横切能力：

- `config`
- `logging`
- `queue_utils`
- 极少量共享类型

`shared/` 不是业务中心层，不允许承载模块专属语义。

### 3.3 组合根

新增 `bootstrap/` 作为唯一组合根，负责：

- 加载配置
- 构建模块
- 连接订阅关系
- 启停生命周期

只有 `bootstrap/` 可以同时了解多个模块的具体装配细节。

## 4. 模块内部结构

每个模块统一采用下列结构：

```text
modules/<name>/
  public.py
  contracts.py
  domain/
  application/
  infrastructure/
```

各层职责：

- `public.py`
  - 唯一允许跨模块访问的公开入口
- `contracts.py`
  - 公开命令、事件、查询结果等稳定契约
- `domain/`
  - 纯业务规则、状态机、值对象
- `application/`
  - 用例编排、输入输出端口、模块内部协调
- `infrastructure/`
  - 技术实现与外部适配器

## 5. 模块协作方式

模块间协作限定为两种形式：

1. 同步公开端口调用
2. 异步公开事件订阅

禁止模块直接共享内部线程、内部队列或内部适配器实例。

推荐数据流：

```text
audio_input
  -> transcription.submit_audio(frame)
  -> transcription emits TranscriptFinalized

wake/vad input
  -> capture.accept_wake(...)
  -> capture.accept_vad(...)
  -> capture.accept_transcript(...)

capture emits CaptureCompleted
  -> injection.execute_capture(...)
  -> storage.store_capture(...)

transcription emits TranscriptFinalized
  -> storage.store_transcript(...)
```

## 6. 公开 API 设计原则

每个模块只暴露有限且稳定的公开入口：

- `TranscriptionModule`
- `CaptureModule`
- `InjectionModule`
- `StorageModule`
- `RuntimeModule`

公开 API 只承担模块边界职责，不暴露内部 worker、内部 queue、内部适配器。

事件对象按两类组织：

- 共享基础类型：放入 `shared/`
- 模块公开契约：放入对应模块的 `contracts.py`

禁止再把所有事件继续集中到单一全局事件文件。

## 7. 依赖规则

依赖矩阵强约束如下：

- `shared` 不依赖任何业务模块
- `domain` 只能依赖本模块 `domain` 与 `shared`
- `application` 只能依赖本模块 `domain` 与 `shared`
- `infrastructure` 只能依赖本模块 `application/domain` 与 `shared`
- 模块之间只能依赖对方 `public.py`
- 只有 `bootstrap/` 可以同时 import 多个模块的具体装配入口

资源所有权约束继续保留并提升为架构规则：

- 只有音频输入模块可访问 `sounddevice`
- 只有存储模块可访问 `sqlite3`
- 只有注入模块可访问 `xdotool` / `ydotool`

## 8. 迁移策略

采用分阶段迁移，避免一次性破坏运行链路。

### 阶段 1：建立新壳与架构约束

- 新增 `modules/`、`bootstrap/`、`shared/`
- 补齐模块 `public.py` / `contracts.py`
- 引入架构测试与 import 约束
- 保持现有运行逻辑不变

### 阶段 2：迁移 `storage` 与 `injection`

- 将低耦合模块先下沉到新结构
- 通过 `public.py` 对外暴露能力

### 阶段 3：迁移 `capture`

- 将捕获逻辑切为模块公开输入输出
- 去除对其他模块内部队列的直接依赖

### 阶段 4：迁移 `transcription`

- 将 ASR 提交与 final 事件输出模块化
- 使 `capture` 与 `storage` 仅依赖 `transcription.public`

### 阶段 5：收口 `runtime` 与删除旧路径

- `bootstrap/` 成为唯一组合根
- 删除旧的 `services/infra/agents/tools` 中重复路径

## 9. 测试与约束

新增架构测试类别：

- 模块依赖方向测试
- 仅通过 `public.py` 跨模块访问测试
- 资源唯一所有者测试

同时保留现有：

- unit：纯逻辑测试
- integration：模块协作测试
- e2e：整条 pipeline 验证

## 10. 风险与缓解

### 风险 1：`shared/` 膨胀为新的 `core`

缓解：
- 只允许稳定横切能力进入 `shared/`
- 新共享项必须证明被多个模块稳定复用

### 风险 2：文件迁移完成但依赖方向未收紧

缓解：
- 先建立架构测试，再迁模块
- 每迁一个模块就同步删除越界 import

### 风险 3：兼容层长期存在，导致新旧双轨

缓解：
- 兼容层仅短期存在
- 每阶段结束前删除上阶段兼容转发

### 风险 4：运行语义被无意改坏

缓解：
- 每阶段只做一个方向的结构变化
- 保持 CLI、配置、线程模型与核心行为不变
- 依赖集成测试与 E2E 回归

## 11. 完成标准

满足以下条件时，认为本次重构达到严格模块化单体目标：

- 顶层边界按业务模块划分
- 模块间跨边界访问只通过 `public.py`
- 组合根集中在 `bootstrap/`
- 架构约束进入测试与 CI
- 旧技术分层目录不再承担主边界职责
