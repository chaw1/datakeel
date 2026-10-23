# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog rebuild commands verify actual event-backed projection hashes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.models import AssetRef
from datakeel.storage.catalog_projection import projection_hash
from datakeel.storage.catalog_store import publish_snapshot

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


def test_rebuild_catalog_when_projection_exists_preserves_canonical_hash(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rebuild the real source object and compare its authoritative event projection."""
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="source:generated",
            objects=(
                CatalogObject(
                    asset_ref=AssetRef(asset_type="source", asset_id="generated"),
                    name="Generated source",
                ),
            ),
        ),
    )
    expected = projection_hash(db)
    invoke("rebuild-catalog", "--expected-hash", expected)
    result = json.loads(capsys.readouterr().out)
    assert result["matches"] is True
    assert result["before_hash"] == result["after_hash"] == expected
    assert result["objects"] == 1


def test_rebuild_catalog_when_expected_hash_wrong_returns_failure(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Expose projection mismatches to command-line callers."""
    with pytest.raises(SystemExit, match="1"):
        invoke("rebuild-catalog", "--expected-hash", "f" * 64)
    assert json.loads(capsys.readouterr().out)["matches"] is False
