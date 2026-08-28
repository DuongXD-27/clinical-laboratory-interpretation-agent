.PHONY: run test lint format-check frontend-lint frontend-test frontend-build check verify clean

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v --basetemp scratch/pytest-make

lint:
	ruff check .

format-check:
	ruff format --check .

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm test

frontend-build:
	cd frontend && npm run build

check: lint test

verify: lint test frontend-lint frontend-test frontend-build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
