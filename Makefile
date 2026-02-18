.PHONY: sync sync-ai run-ai check-ai test run lint fmt check precommit

sync:
	uv sync --group dev

sync-ai:
	uv sync --python 3.11 --group dev --group runtime-ai

run-ai: sync-ai
	uv run --python 3.11 python -m asr_ol --config config/config.yaml

check-ai: sync-ai
	uv run --python 3.11 python scripts/check_runtime_ai.py

test:
	uv run pytest -q

run:
	uv run python -m asr_ol --config config/config.yaml

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests

check: lint test

precommit:
	uv run pre-commit run --all-files
