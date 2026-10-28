# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reading services bind the actual operation scope instead of trusting a caller label."""

from pathlib import Path
from typing import Literal

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.data_asset_models import AccessContext, AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import resolve_download
from datakeel.storage.lineage_service import export_dataset, export_events
from tests.assets.entry_helpers import EntryResources, grant, publish, seed_resources


def _read(
    db: Database,
    resources: EntryResources,
    entry: str,
    access: AccessContext,
) -> None:
    if entry == "download":
        resolve_download(db, resources.dataset_id, resources.file_id, access=access)
    elif entry == "export":
        export_dataset(db, resources.dataset_id, "http://fixture.invalid", access=access)
    else:
        export_events(db, resources.dataset_id, access=access)


@pytest.mark.parametrize("entry", ["download", "export", "lineage"])
def test_service_scope_cannot_be_relabelled_as_query(
    db: Database, tmp_path: Path, entry: Literal["download", "export", "lineage"]
) -> None:
    """A query grant cannot authorize downloading or either export format."""
    resources = seed_resources(db, tmp_path)
    asset = publish(db, AssetRef(asset_id=resources.dataset_id))
    assert grant(db, asset, "valid", "query")
    mislabelled = AccessContext(actor="local", entry="ask", scope="query")
    with pytest.raises(AuthorizationError, match="apply for access"):
        _read(db, resources, entry, mislabelled)
    assert list_usage(db, AssetUsageQuery()) == ()
    actual_scope = "download" if entry == "download" else "export"
    grant_id = grant(db, asset, "valid", actual_scope)
    _read(db, resources, entry, mislabelled)
    usages = list_usage(db, AssetUsageQuery())
    assert len(usages) == 1
    assert usages[0].scope == usages[0].entry == actual_scope
    assert usages[0].grant_id == grant_id


def test_ask_scope_cannot_be_relabelled_as_download(db: Database, tmp_path: Path) -> None:
    """Ask preserves the trusted operator and entrance but always requires query scope."""
    seed_resources(db, tmp_path)
    asset = publish(db, AssetRef(asset_type="metric", asset_id="retail_revenue"))
    assert grant(db, asset, "valid", "download")
    with pytest.raises(AuthorizationError, match="active query grant"):
        ask_data(
            db,
            AskRequest(
                question="上个季度华东区零售额是多少",
                reference_instant="2026-10-01T00:00:00Z",
            ),
            access=AccessContext(actor="local", entry="mcp", scope="download"),
        )
    assert list_usage(db, AssetUsageQuery()) == ()
