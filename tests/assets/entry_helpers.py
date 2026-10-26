# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated resources and real authorization facts for cross-entry regressions."""

from datetime import timedelta
from pathlib import Path
from typing import Literal

from datakeel.core.data_asset_models import (
    AccessScope,
    AssetApplicationInput,
    AssetClassification,
    AssetMutationContext,
    DataAsset,
    DataAssetDefinition,
)
from datakeel.core.models import AssetRef, BoundaryModel, new_id, utcnow
from datakeel.storage.data_asset_grants import (
    decide_application_in_session,
    revoke_grant_in_session,
    submit_application,
)
from datakeel.storage.data_asset_store import create_asset_in_session, set_status_in_session
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_files
from tests.enterprise_support import enterprise_fixture

type GrantState = Literal["none", "expired", "revoked", "wrong_scope", "valid"]


class EntryResources(BoundaryModel):
    """Bind a metric and a downloadable generated dataset without source dependencies."""

    dataset_id: str
    file_id: str


def seed_resources(db: Database, directory: Path) -> EntryResources:
    """Install local business SQL and a single generated downloadable document."""
    enterprise_fixture(db, directory / "enterprise")
    document = directory / "sample.txt"
    document.write_text("Generated asset access sample.")
    dataset = import_paths(db, "Generated controlled asset", [document])
    return EntryResources(dataset_id=dataset.id, file_id=list_files(db, dataset.id)[0].id)


def publish(
    db: Database, target: AssetRef, classification: AssetClassification = "restricted"
) -> DataAsset:
    """Seed a published policy inside the same transaction used by controlled actions."""
    with db.session() as session:
        db.lock_writes(session)
        draft = create_asset_in_session(
            session,
            DataAssetDefinition(
                target=target,
                name="Generated asset",
                owner="fixture-owner",
                classification=classification,
            ),
            AssetMutationContext(actor="local", operation_id=new_id()),
        )
        asset = set_status_in_session(
            session,
            draft.id,
            "published",
            AssetMutationContext(actor="local", operation_id=new_id()),
        )
        session.commit()
        return asset


def grant(
    db: Database, asset: DataAsset, state: GrantState, scope: AccessScope, *, subject: str = "local"
) -> str | None:
    """Build expiry with injected clocks; never wait for a real timer."""
    if state == "none":
        return None
    now = utcnow()
    started = now - timedelta(hours=2) if state == "expired" else now - timedelta(minutes=1)
    expires = started + timedelta(hours=1)
    scopes: tuple[AccessScope, ...] = (
        (("export",) if scope == "query" else ("query",)) if state == "wrong_scope" else (scope,)
    )
    application = submit_application(
        db,
        AssetApplicationInput(
            asset_id=asset.id,
            purpose="Generated access regression",
            scopes=scopes,
            expires_at=expires,
        ),
        subject,
        now=started,
    )
    with db.session() as session:
        db.lock_writes(session)
        decided = decide_application_in_session(
            session,
            application.id,
            AssetMutationContext(actor="local", operation_id=new_id()),
            approved=True,
            now=started,
        )
        assert decided.grant_id
        if state == "revoked":
            revoke_grant_in_session(
                session,
                decided.grant_id,
                AssetMutationContext(actor="local", operation_id=new_id()),
                now=now,
            )
        session.commit()
        return decided.grant_id


def revoke(db: Database, grant_id: str) -> None:
    """Retire an entry-specific grant before the next matrix probe."""
    with db.session() as session:
        db.lock_writes(session)
        revoke_grant_in_session(
            session, grant_id, AssetMutationContext(actor="local", operation_id=new_id())
        )
        session.commit()
