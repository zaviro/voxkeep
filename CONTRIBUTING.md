# Contributing

## Development Setup

1. Install Python `3.11` and `uv`.
2. Sync dependencies:

```bash
make sync
```

3. Optional runtime-ai dependencies:

```bash
make sync-ai
```

4. Validate local environment and config before runtime work:

```bash
make doctor
make validate-config
```

5. If you need to honor `config/config.yaml` exactly, run the CLI directly:

```bash
uv run --python 3.11 python -m voxkeep run --config config/config.yaml
```

`make run` is the primary way to start the local development runtime using the default `config/config.yaml`.

## Quality Gates

Run these checks before opening a PR:

```bash
make cli-check
make lint
make test
make typecheck
make test-cov
```

## Commit Convention

Use Conventional Commits:

- `feat: ...`
- `fix: ...`
- `refactor: ...`
- `test: ...`
- `chore: ...`

Keep commits focused and atomic.

## Pull Requests

PRs should include:

- Summary of changes and rationale.
- Test evidence (commands + outcomes).
- Config/runtime impact (ASR backend or endpoint, audio devices, wake model, injector backend) if relevant.

## Testing Notes

- Unit and integration tests are in `tests/unit` and `tests/integration`.
- E2E tests are in `tests/e2e`; some require opt-in env vars.
- `make doctor` is the preferred first-stop command when local runtime checks fail.
- `make validate-config` validates `config/config.yaml` plus `VOXKEEP_*` environment overrides.
- `backend current` and `backend doctor` are the preferred backend-specific checks before blaming runtime code:

```bash
uv run --python 3.11 python -m voxkeep backend current --config config/config.yaml
uv run --python 3.11 python -m voxkeep backend doctor --config config/config.yaml
```

`backend doctor` reports backend health classification and may return `assets_missing` before any live endpoint probe if the persisted asset state is absent.

- GPT-SoVITS E2E 使用预生成夹具，首次执行：

```bash
.codex/skills/gptsovits-cli-tts/scripts/generate_test_fixtures.sh
```

- 默认 API 启动脚本：`~/workspace/gptsovits/scripts/start_api_cuda.sh`。
- 运行 GPT-SoVITS 夹具 E2E：

```bash
VOXKEEP_RUN_GPTSOVITS_E2E=1 uv run --python 3.11 python -m pytest tests/e2e/test_pipeline_tts_audio.py -q
```
