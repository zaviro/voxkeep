.PHONY: sync sync-ai setup-ai-models run-ai check-ai doctor validate-config cli-check test test-cov typecheck run lint fmt check precommit

sync:
	uv sync --python 3.11 --group dev

sync-ai:
	uv sync --python 3.11 --group dev --group runtime-ai

setup-ai-models: sync-ai
	uv run --python 3.11 python scripts/setup_openwakeword_models.py

run-ai: setup-ai-models
	./scripts/run_local.sh config/config.yaml

check-ai: setup-ai-models
	uv run --python 3.11 python scripts/check_runtime_ai.py

doctor:
	uv run --python 3.11 python -m voxkeep doctor

validate-config:
	uv run --python 3.11 python -m voxkeep config validate --config config/config.yaml

cli-check:
	uv run --python 3.11 python -m voxkeep check

test:
	uv run --python 3.11 python -m pytest -q

test-cov:
	uv run --python 3.11 python -m pytest --cov=src/voxkeep --cov-report=term --cov-report=xml

typecheck:
	uv run --python 3.11 pyright

run:
	./scripts/run_local.sh config/config.yaml

lint:
	uv run --python 3.11 ruff check src tests scripts

fmt:
	uv run --python 3.11 ruff format src tests scripts

check: lint test

precommit:
	uv run --python 3.11 pre-commit run --all-files
