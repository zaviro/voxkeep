.PHONY: sync sync-ai setup-ai-models run-ai check-ai test run lint fmt check precommit

sync:
	uv sync --python 3.11 --group dev

sync-ai:
	uv sync --python 3.11 --group dev --group runtime-ai

setup-ai-models: sync-ai
	uv run --python 3.11 python scripts/setup_openwakeword_models.py

run-ai: setup-ai-models
	uv run --python 3.11 python -m asr_ol --config config/config.yaml

check-ai: setup-ai-models
	uv run --python 3.11 python scripts/check_runtime_ai.py

test:
	uv run --python 3.11 pytest -q

run:
	uv run --python 3.11 python -m asr_ol --config config/config.yaml

lint:
	uv run --python 3.11 ruff check src tests

fmt:
	uv run --python 3.11 ruff format src tests

check: lint test

precommit:
	uv run --python 3.11 pre-commit run --all-files
