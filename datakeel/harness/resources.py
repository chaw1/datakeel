# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Locate checked-in contracts in a source checkout or installed wheel."""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def contract_path(name: str) -> Path:
    """Prefer repository contracts and fall back to bundled installation resources."""
    source = PACKAGE_ROOT.parent / "contracts" / name
    return source if source.exists() else PACKAGE_ROOT / "_contracts" / name
