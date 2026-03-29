# Project Hardening Design

**Date:** 2026-03-30

## Goal

提高仓库默认质量检查的稳定性与可信度，避免外部系统状态导致本地/CI 全量测试误红，同时让静态类型检查覆盖到当前主干实现。

## Scope

1. 将真实 `openclaw` 调用测试改为显式启用。
2. 将 `pyright` 覆盖范围扩大到整个 `src/asr_ol`。
3. 修复扩大覆盖后暴露出的真实类型问题。

## Chosen Approach

采用“默认稳定、显式开启真实链路”的策略：

- 默认 `pytest` 不直接调用真实 `openclaw` agent。
- 只有设置 `ASR_OL_RUN_OPENCLAW_REAL=1` 时，才执行真实 `openclaw` 集成链路。
- 保留真实测试本身，避免完全退化为 mock。
- `pyright` 直接覆盖整个包，用修复真实问题代替继续缩小检查范围。

## Validation

- `uv run --python 3.11 python -m pytest -q`
- `uv run --python 3.11 ruff check src tests scripts`
- `uv run --python 3.11 pyright`
