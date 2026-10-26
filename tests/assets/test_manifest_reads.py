# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native file listings cannot disclose protected metadata through a manifest preview."""

from pathlib import Path
from typing import Literal

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AssetClassification, AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef, FileItem
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.dataset_service import list_files, list_versions
from tests.assets.entry_helpers import grant, publish, revoke

_CAPTION = "Generated protected caption for the manifest read regression."


def _manifest(db: Database, directory: Path) -> tuple[str, str]:
    document = directory / "source.txt"
    document.write_text(_CAPTION)
    file = FileItem(
        filename=document.name,
        path=str(document),
        modality="text",
        metadata={"caption_text": _CAPTION},
    )
    with db.session() as session:
        files = [file.model_dump(mode="json")]
        dataset = DatasetRow(name="Generated manifest", files=files)
        session.add(dataset)
        session.flush()
        version = VersionRow(dataset_id=dataset.id, manifest=files)
        session.add(version)
        session.flush()
        identities = dataset.id, version.id
        session.commit()
        return identities


@pytest.mark.parametrize("classification", ["request", "restricted"])
@pytest.mark.parametrize("reader", ["files", "versioned_files", "versions"])
def test_manifest_views_require_current_query_permission(
    db: Database,
    tmp_path: Path,
    classification: AssetClassification,
    reader: Literal["files", "versioned_files", "versions"],
) -> None:
    """Actual HTTP and default CLI services deny caption disclosure after grant revocation."""
    dataset_id, version_id = _manifest(db, tmp_path)
    asset = publish(db, AssetRef(asset_id=dataset_id), classification)
    endpoint = f"/api/datasets/{dataset_id}/{'versions' if reader == 'versions' else 'files'}"
    params = {"version": version_id} if reader == "versioned_files" else {}
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        response = client.get(endpoint, params=params)
        assert response.status_code == 403
        assert "apply for access" in response.text
        assert _CAPTION not in response.text
        grant(db, asset, "valid", "download")
        assert client.get(endpoint, params=params).status_code == 403
        query_grant = grant(db, asset, "valid", "query")
        assert query_grant is not None
        response = client.get(endpoint, params=params)
        assert response.status_code == 200
        assert _CAPTION in response.text
        # CLI listing uses its own default operator, rather than borrowing the HTTP grant.
        if reader == "versions":
            with pytest.raises(AuthorizationError):
                list_versions(db, dataset_id)
        else:
            with pytest.raises(AuthorizationError):
                list_files(db, dataset_id, version_id if params else None)
        revoke(db, query_grant)
        response = client.get(endpoint, params=params)
        assert response.status_code == 403
        assert _CAPTION not in response.text
    usages = list_usage(db, AssetUsageQuery(asset_id=asset.id))
    assert len(usages) == 1
    assert (usages[0].actor, usages[0].entry, usages[0].scope) == ("local", "ask", "query")
    assert usages[0].grant_id == query_grant
