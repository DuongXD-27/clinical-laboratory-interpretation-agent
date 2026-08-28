.PHONY: run lint format format-check test frontend-lint frontend-test frontend-build verify

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest -v --basetemp scratch/pytest-make

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm test

frontend-build:
	cd frontend && npm run build

verify: lint format-check test frontend-lint frontend-test frontend-build
	python scripts/check_tracked_generated_artifacts.py
