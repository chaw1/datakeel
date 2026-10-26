# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Query service boundaries own their required scope rather than trusting caller context."""

from pathlib import Path

import pytest

from datakeel.core.data_asset_models import AccessContext, AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.data_asset_reads import authorize_query
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from tests.assets.entry_helpers import grant, publish


def test_query_service_ignores_mismatched_download_scope(db: Database, tmp_path: Path) -> None:
    """A download grant cannot authorize queries when the caller supplies the wrong scope."""
    path = tmp_path / "generated.txt"
    path.write_text("Generated scope regression", encoding="utf-8")
    dataset = import_paths(db, "Scope regression", [path])
    ref = AssetRef(asset_id=dataset.id)
    asset = publish(db, ref)
    grant(db, asset, "valid", "download")
    caller = AccessContext(actor="local", entry="ask", scope="download")
    with pytest.raises(AuthorizationError, match="query grant"):
        authorize_query(db, (ref,), caller)
    assert list_usage(db, AssetUsageQuery(asset_id=asset.id)) == ()
    grant(db, asset, "valid", "query")
    authorize_query(db, (ref,), caller)
    usage = list_usage(db, AssetUsageQuery(asset_id=asset.id))
    assert len(usage) == 1
    assert usage[0].scope == "query"
