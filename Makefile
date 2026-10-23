.PHONY: check fix check-python check-web check-licenses

check: check-python check-web check-licenses

check-python:
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run lint-imports
	uv run python scripts/check_size.py
	uv run python scripts/check_boundaries.py
	uv run python scripts/check_web_tests.py
	uv run pytest --cov=datakeel --cov-report=term-missing --cov-report=xml --cov-report=json --cov-fail-under=85
	uv run python scripts/check_coverage.py

check-web:
	cd web && npm run check:source && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run check:source

check-licenses: check-web
	uv run python scripts/license_audit.py

fix:
	uv run ruff format .
	uv run ruff check --fix .
	cd web && npx prettier --write .
