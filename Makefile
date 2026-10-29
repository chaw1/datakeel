.PHONY: check fix check-public check-python check-web check-licenses check-rust check-scale

check: check-public check-rust check-python check-scale check-web check-licenses

check-public:
	uv run python scripts/check_public_worktree.py

check-rust:
	@command -v cargo >/dev/null 2>&1 || { echo "Rust toolchain required: install cargo, rustfmt and clippy with https://rustup.rs/"; exit 1; }
	cd accel && cargo fmt --check
	cd accel && PYO3_PYTHON=$(abspath .venv/bin/python) cargo clippy --locked -- -D warnings
	cd accel && PYO3_PYTHON=$(abspath .venv/bin/python) cargo test --locked
	uv run python -m scripts.license_rust --write-notices
	@mkdir -p accel/dist
	@set -eu; wheel_dir=$$(mktemp -d accel/dist/check.XXXXXX); \
	  RUSTFLAGS="$(RUSTFLAGS) --remap-path-prefix=$(HOME)=/build --remap-path-prefix=$(CURDIR)=/src" \
	    uv run maturin build --release --locked --manifest-path accel/Cargo.toml --out "$$wheel_dir"; \
	  uv run python scripts/check_accel_wheel.py "$$wheel_dir"/*.whl; \
	  uv pip install --python .venv/bin/python --no-deps --force-reinstall "$$wheel_dir"/*.whl
	uv run pyright accel/python/datakeel_accel
	uv run pytest tests/operators/evidence/test_near_duplicate_accel.py

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

check-scale:
	uv run python -m scripts.scale_bench.smoke --verify-mutation

check-web:
	cd web && npm run check:source && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run check:source

check-licenses: check-web
	uv run python scripts/license_audit.py

fix:
	uv run ruff format .
	uv run ruff check --fix .
	cd web && npx prettier --write .
