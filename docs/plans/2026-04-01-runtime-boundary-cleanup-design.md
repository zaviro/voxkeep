# Runtime Boundary Cleanup Design

**Date:** 2026-04-01

## Goal

在不改变 CLI、配置语义、事件形状和运行时行为的前提下，收口模块化重构遗留的过渡层，降低后续演进时的耦合与认知成本。

## Scope

1. 收口 `bootstrap` 与模块边界，去掉私有属性和私有方法穿透。
2. 拆分 `shared/config.py` 的装载职责，保留对外兼容入口。
3. 迁正测试目录与文档引用，使仓库结构表达当前模块化架构。

## Current Problems

- `bootstrap/runtime_app.py` 仍然直接依赖具体 wake/VAD 基础设施实现，并读取模块私有属性。
- 部分 `public.py` 仍然是对 legacy worker 的过渡封装，甚至调用私有方法完成行为穿透。
- `shared/config.py` 同时负责 schema、默认值、环境变量映射、装载与校验，已经接近共享层热点。
- 测试目录与若干文档仍保留 `core`、`infra`、`services`、`agents`、`tools` 等迁移期语义，不利于新架构表达。

## Chosen Approach

采用分阶段、兼容式收口：

- `P0` 先处理最容易继续腐化的运行时边界问题。
- `P1` 再拆分配置装载层，保持 `AppConfig` 和 `load_config` 的兼容出口。
- `P2` 最后迁正测试与文档命名，统一仓库认知模型。

每个阶段都独立验证并原子提交，避免一次性大重构导致定位困难。

## Design Details

### P0: Runtime Boundary Tightening

- 在 `transcription` 模块 public API 中增加显式诊断接口，替代 `bootstrap` 对 `_engine` 的读取。
- 将 wake/VAD worker 的构建职责下沉到稳定 builder 层，避免 `bootstrap` 直接依赖具体类名。
- 为 injection public API 增加显式执行路径，避免调用 worker 私有方法。
- 保持现有生命周期顺序、队列连接方式和 worker 健康检查逻辑不变。

### P1: Config Loader Split

- 保留 `voxkeep.shared.config` 作为兼容入口。
- 将配置拆成四类职责：
  - schema/dataclass
  - defaults
  - env override map
  - loader/merge/validate
- 外部调用仍保持 `from voxkeep.shared.config import AppConfig, WakeRuleConfig, load_config`。

### P2: Test and Docs Alignment

- 将遗留的测试目录按当前模块边界迁移到 `shared`、`bootstrap`、`modules/...`。
- 更新 `AGENTS.md` 与 `docs/plans/*` 中仍引用旧路径的内容。
- 如有必要，补充约束测试，避免后续继续新增迁移期命名。

## Non-Goals

- 不替换现有 wake/VAD/ASR/injector 后端。
- 不修改事件 payload 或 CLI 行为。
- 不引入新的运行时功能。
- 不进行推倒式目录重构。

## Validation

- `uv run --python 3.11 python -m pytest tests/architecture -q`
- `uv run --python 3.11 python -m pytest tests/unit/bootstrap/test_runtime_app.py -q`
- `uv run --python 3.11 python -m pytest tests/unit/shared/test_config.py -q`
- `uv run --python 3.11 python -m pytest tests/unit -q`
- `make validate-config`
