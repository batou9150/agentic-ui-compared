.PHONY: install test lint typecheck fixtures

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy core/src

# Re-record Open-Meteo fixtures (a few dozen live requests, run sparingly).
fixtures:
	uv run python scripts/record_fixtures.py
