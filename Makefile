.PHONY: check fix check-public check-python check-python-static check-pytest check-coverage check-web check-licenses check-rust install-accel check-scale collect-tests check-test-shards combine-coverage

# CI runs one whole-module pytest shard per job (PYTEST_SHARD=K/N) and merges their coverage
# with combine-coverage; locally PYTEST_SHARD stays empty and the whole suite runs at once.
PYTEST_SHARD ?=
PYTEST_SHARDS ?= 4
CI_ARTIFACTS ?= artifacts/ci
PYTEST_SHARD_ARGS = $(if $(PYTEST_SHARD),-p scripts.pytest_shards --shard=$(PYTEST_SHARD) --shard-report=$(CI_ARTIFACTS)/pytest/shard-$(subst /,-of-,$(PYTEST_SHARD)))

check: check-public check-rust check-python check-scale check-web check-licenses

check-public:
	uv run python scripts/check_public_worktree.py

check-rust:
	@command -v cargo >/dev/null 2>&1 || { echo "Rust toolchain required: install cargo, rustfmt and clippy with https://rustup.rs/"; exit 1; }
	cd accel && cargo fmt --check
	cd accel && PYO3_PYTHON=$(abspath .venv/bin/python) cargo clippy --locked -- -D warnings
	cd accel && PYO3_PYTHON=$(abspath .venv/bin/python) cargo test --locked
	@$(MAKE) --no-print-directory install-accel
	uv run pyright accel/python/datakeel_accel
	uv run pytest tests/operators/evidence/test_near_duplicate_accel.py

# Build, verify and install the optional extension; test jobs need it to import accel tests.
install-accel:
	@command -v cargo >/dev/null 2>&1 || { echo "Rust toolchain required: install cargo, rustfmt and clippy with https://rustup.rs/"; exit 1; }
	uv run python -m scripts.license_rust --write-notices
	@mkdir -p accel/dist
	@set -eu; wheel_dir=$$(mktemp -d accel/dist/check.XXXXXX); \
	  RUSTFLAGS="$(RUSTFLAGS) --remap-path-prefix=$(HOME)=/build --remap-path-prefix=$(CURDIR)=/src" \
	    uv run maturin build --release --locked --manifest-path accel/Cargo.toml --out "$$wheel_dir"; \
	  uv run python scripts/check_accel_wheel.py "$$wheel_dir"/*.whl; \
	  uv pip install --python .venv/bin/python --no-deps --force-reinstall "$$wheel_dir"/*.whl

check-python: check-python-static check-pytest check-coverage

check-python-static:
	uv run ruff format --check .
	uv run ruff check .
	uv run pyright
	uv run lint-imports
	uv run python scripts/check_size.py
	uv run python scripts/check_boundaries.py
	uv run python scripts/check_web_tests.py

check-pytest:
	uv run python -m scripts.run_pytest $(PYTEST_SHARD_ARGS) --cov=datakeel --cov-report=

# The same 85% total line as pytest-cov's --cov-fail-under, then the per-module lines.
check-coverage:
	uv run coverage report --show-missing --fail-under=85
	uv run coverage report --format=total --precision=2
	uv run coverage xml
	uv run coverage json
	uv run python scripts/check_coverage.py

collect-tests:
	uv run pytest --collect-only -qq -p scripts.pytest_shards --shard-report=$(CI_ARTIFACTS)/collection

combine-coverage:
	uv run coverage combine $(CI_ARTIFACTS)/coverage

check-test-shards:
	uv run python -m scripts.check_pytest_shards --collection $(CI_ARTIFACTS)/collection --shards $(CI_ARTIFACTS)/pytest --count $(PYTEST_SHARDS)

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
