# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version-owned file reads inherit real controlled derivation without guessing sources."""

from pathlib import Path
from typing import NamedTuple

import pytest
from sqlalchemy import select

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.assets.access import require_access
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef, FileItem, JsonDocument
from datakeel.storage.data_asset_targets import resolve_access_targets
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import import_paths, resolve_download
from datakeel.storage.datasets import persist_file
from tests.assets.entry_helpers import grant, publish

DOWNLOAD = AccessContext(actor="reader", entry="download", scope="download")


class NativeSource(NamedTuple):
    """Keep the exact original file and version used by a controlled selection."""

    dataset_id: str
    version_id: str
    file: FileItem


def _source(db: Database, directory: Path) -> NativeSource:
    document = directory / "source.txt"
    document.write_text("Generated protected original bytes.")
    dataset = import_paths(db, "Generated version source", [document])
    with db.session() as session:
        version = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        assert version is not None
        return NativeSource(dataset.id, version.id, FileItem.model_validate(version.manifest[0]))


def _derive(db: Database, source: NativeSource) -> AssetRef:
    plan = prepare_action(
        db,
        "create_version_from_selection",
        JsonDocument(
            {
                "selection": {
                    "dataset_id": source.dataset_id,
                    "version_ids": [source.version_id],
                    "filters": [{"field": "id", "operator": "in", "value": [source.file.id]}],
                },
                "name": "Generated controlled selection",
            }
        ),
    )
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert result.status == "SUCCEEDED"
    assert result.receipt is not None
    return next(ref for ref in result.receipt.outputs if ref.asset_type == "version")


def test_controlled_derived_version_file_requires_its_protected_source_grant(
    db: Database, tmp_path: Path
) -> None:
    """Actual controlled V1→V2 publication cannot make V1's protected bytes public."""
    source = _source(db, tmp_path)
    policy = publish(db, AssetRef(asset_id=source.dataset_id, version=source.version_id))
    grant(db, policy, "valid", "query")
    derived = _derive(db, source)
    file_ref = AssetRef(asset_type="file", asset_id=source.file.id, version=derived.asset_id)
    with pytest.raises(AuthorizationError):
        require_access(db, (file_ref,), DOWNLOAD)
    with pytest.raises(AuthorizationError):
        resolve_download(db, source.dataset_id, source.file.id, derived.asset_id, access=DOWNLOAD)
    with db.session() as session:
        refs = resolve_access_targets(session, (file_ref,))
    assert derived in refs
    assert AssetRef(asset_id=source.dataset_id, version=source.version_id) in refs
    grant(db, policy, "valid", "download", subject="reader")
    assert [item.asset_id for item in require_access(db, (file_ref,), DOWNLOAD)] == [policy.id]
    downloaded = resolve_download(
        db, source.dataset_id, source.file.id, derived.asset_id, access=DOWNLOAD
    )
    assert downloaded.path.read_text() == "Generated protected original bytes."


def test_independent_version_file_does_not_inherit_unrelated_old_version_policy(
    db: Database, tmp_path: Path
) -> None:
    """Different V2 bytes with no derivation from protected V1 remain independently readable."""
    source = _source(db, tmp_path)
    publish(db, AssetRef(asset_id=source.dataset_id, version=source.version_id))
    replacement_path = tmp_path / "independent.txt"
    replacement_path.write_text("Generated independent replacement bytes.")
    replacement = persist_file(source.file.model_copy(update={"path": str(replacement_path)}))
    with db.session() as session:
        version = VersionRow(
            dataset_id=source.dataset_id,
            manifest=[replacement.model_dump(mode="json")],
        )
        session.add(version)
        session.flush()
        version_id = version.id
        session.commit()
    file_ref = AssetRef(asset_type="file", asset_id=source.file.id, version=version_id)
    with db.session() as session:
        refs = resolve_access_targets(session, (file_ref,))
    assert AssetRef(asset_id=source.dataset_id, version=source.version_id) not in refs
    assert require_access(db, (file_ref,), DOWNLOAD) == ()
    downloaded = resolve_download(
        db, source.dataset_id, source.file.id, version_id, access=DOWNLOAD
    )
    assert downloaded.path.read_text() == "Generated independent replacement bytes."
