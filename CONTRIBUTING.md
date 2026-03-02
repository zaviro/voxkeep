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

## Quality Gates

Run these checks before opening a PR:

```bash
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
- Config/runtime impact (audio devices, wake model, FunASR endpoint) if relevant.

## Testing Notes

- Unit and integration tests are in `tests/unit` and `tests/integration`.
- E2E tests are in `tests/e2e`; some require opt-in env vars.
