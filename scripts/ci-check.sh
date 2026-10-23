#!/usr/bin/env bash
set -euo pipefail
cd web
npm run check:source
cd ..
make check
cd web
npm run check:source
cd ..
uv run python scripts/check_readme.py
uv run python scripts/mutate.py
