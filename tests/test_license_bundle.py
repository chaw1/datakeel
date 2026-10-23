# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bundle evidence must match current source bytes and safe locked package locations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from scripts.license_bundle import bundle_packages
from tests.test_license_frontend import write_frontend, write_inventory

if TYPE_CHECKING:
    from pathlib import Path


def test_bundle_inventory_rejects_missing_and_stale_build_evidence(tmp_path: Path) -> None:
    """A prior successful audit cannot excuse changed source or an absent measured inventory."""
    web = write_frontend(tmp_path)
    assert bundle_packages(tmp_path) == ("node_modules/leaf", "node_modules/runtime")
    (web / "src/main.js").write_text("import 'changed';\n")
    with pytest.raises(ValidationError, match="stale"):
        bundle_packages(tmp_path)
    inventory = write_inventory(tmp_path)
    inventory.unlink()
    with pytest.raises(ValidationError, match="missing"):
        bundle_packages(tmp_path)


@pytest.mark.parametrize(
    "packages",
    [
        ("node_modules/z", "node_modules/a"),
        ("node_modules/a", "node_modules/a"),
        ("node_modules/../outside",),
        ("node_modules//invalid",),
        ("outside/package",),
    ],
)
def test_bundle_inventory_rejects_unsafe_or_ambiguous_locations(
    tmp_path: Path, packages: tuple[str, ...]
) -> None:
    """Only sorted, unique npm package locations may select installed license metadata."""
    write_frontend(tmp_path)
    write_inventory(tmp_path, packages)
    with pytest.raises(ValidationError):
        bundle_packages(tmp_path)


def test_bundle_inventory_rejects_symbolic_source_entries(tmp_path: Path) -> None:
    """The Python and JavaScript hash contracts both reject unsupported source links."""
    web = write_frontend(tmp_path)
    (web / "src/linked.js").symlink_to(web / "src/main.js")
    with pytest.raises(ValidationError, match="symbolic"):
        bundle_packages(tmp_path)
