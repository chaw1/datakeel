# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled asset revisions, existing-target validation and immutable history."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import (
    AssetHistory,
    AssetMutationContext,
    AssetStatus,
    DataAsset,
    DataAssetDefinition,
)
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import AssetRef, new_id, utcnow
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.data_asset_rows import DataAssetHistoryRow, DataAssetRow
from datakeel.storage.database import Database, DatasetRow, VersionRow


def asset_in_session(session: Session, asset_id: str) -> DataAsset:
    """Read one current asset inside the caller's transaction."""
    row = session.get(DataAssetRow, asset_id)
    if row is None:
        msg = f"Data asset not found: {asset_id}"
        raise NotFoundError(msg)
    return DataAsset.model_validate(row.payload)


def get_asset(db: Database, asset_id: str) -> DataAsset:
    """Read one current immutable asset snapshot."""
    with db.session() as session:
        return asset_in_session(session, asset_id)


def assets_in_session(session: Session) -> tuple[DataAsset, ...]:
    """Read every current asset in stable identity order."""
    return tuple(
        DataAsset.model_validate(row.payload)
        for row in session.scalars(select(DataAssetRow).order_by(DataAssetRow.id))
    )


def list_assets(db: Database) -> tuple[DataAsset, ...]:
    """List assets including drafts for the local management surface."""
    with db.session() as session:
        return assets_in_session(session)


def validate_asset_target(session: Session, definition: DataAssetDefinition) -> None:
    """Require the referenced dataset, version, table or metric to exist."""
    validate_target(session, definition.target)


def validate_target(session: Session, ref: AssetRef) -> None:
    """Validate one native target before preparing a controlled asset action."""
    if ref.asset_type == "dataset":
        dataset = session.get(DatasetRow, ref.asset_id)
        version = session.get(VersionRow, ref.version) if ref.version else None
        if dataset is not None and (
            ref.version is None or (version is not None and version.dataset_id == dataset.id)
        ):
            return
    else:
        for item in read_snapshot(session).objects:
            if (
                item.asset_ref.asset_type == ref.asset_type
                and item.asset_ref.asset_id == ref.asset_id
                and (ref.version is None or ref.version == item.asset_ref.version)
            ):
                return
    msg = f"Asset target not found: {ref.asset_type}:{ref.asset_id}"
    raise ValidationError(msg)


def _replay(
    session: Session,
    context: AssetMutationContext,
    action: str,
) -> DataAsset | None:
    row = session.scalar(
        select(DataAssetHistoryRow).where(DataAssetHistoryRow.operation_id == context.operation_id)
    )
    if row is None:
        return None
    history = AssetHistory.model_validate(row.payload)
    if history.actor != context.actor or history.action != action:
        msg = "Asset operation identity already binds another actor or action"
        raise ConflictError(msg)
    return history.asset


def _same_definition(
    asset: DataAsset,
    definition: DataAssetDefinition,
    asset_id: str | None = None,
) -> None:
    if asset.definition != definition or (asset_id is not None and asset.id != asset_id):
        msg = "Asset operation identity already binds another definition or asset"
        raise ConflictError(msg)


def _record(
    session: Session, asset: DataAsset, context: AssetMutationContext, action: str
) -> DataAsset:
    history = AssetHistory(
        id=new_id(),
        asset_id=asset.id,
        operation_id=context.operation_id,
        actor=context.actor,
        action=action,
        occurred_at=asset.updated_at,
        asset=asset,
    )
    row = session.get(DataAssetRow, asset.id)
    if row:
        row.payload = asset.model_dump(mode="json")
    else:
        session.add(DataAssetRow(id=asset.id, payload=asset.model_dump(mode="json")))
        session.flush()
    session.add(
        DataAssetHistoryRow(
            id=history.id,
            asset_id=asset.id,
            operation_id=context.operation_id,
            payload=history.model_dump(mode="json"),
        )
    )
    session.flush()
    return asset


def create_asset_in_session(
    session: Session, definition: DataAssetDefinition, context: AssetMutationContext
) -> DataAsset:
    """Create one draft within the existing controlled action transaction."""
    replay = _replay(session, context, "create")
    if replay:
        _same_definition(replay, definition)
        return replay
    validate_asset_target(session, definition)
    now = utcnow()
    asset = DataAsset(
        id=new_id(),
        revision=1,
        definition=definition,
        created_at=now,
        updated_at=now,
    )
    return _record(session, asset, context, "create")


def _current(session: Session, asset_id: str, context: AssetMutationContext) -> DataAsset:
    row = session.scalar(select(DataAssetRow).where(DataAssetRow.id == asset_id).with_for_update())
    if row is None:
        msg = f"Data asset not found: {asset_id}"
        raise NotFoundError(msg)
    asset = DataAsset.model_validate(row.payload)
    if context.expected_revision is not None and context.expected_revision != asset.revision:
        msg = f"Expected asset revision {context.expected_revision}; current is {asset.revision}"
        raise ConflictError(msg)
    return asset


def update_asset_in_session(
    session: Session,
    asset_id: str,
    definition: DataAssetDefinition,
    context: AssetMutationContext,
) -> DataAsset:
    """Replace documentation while retaining status and prior immutable revisions."""
    replay = _replay(session, context, "update")
    if replay:
        _same_definition(replay, definition, asset_id)
        return replay
    before = _current(session, asset_id, context)
    validate_asset_target(session, definition)
    if definition.target != before.definition.target:
        msg = "An existing asset cannot be retargeted; create another asset"
        raise ValidationError(msg)
    asset = before.model_copy(
        update={
            "revision": before.revision + 1,
            "definition": definition,
            "updated_at": utcnow(),
        }
    )
    return _record(session, asset, context, "update")


def set_status_in_session(
    session: Session, asset_id: str, status: AssetStatus, context: AssetMutationContext
) -> DataAsset:
    """Publish or withdraw a revision without deleting its access policy."""
    replay = _replay(session, context, status)
    if replay:
        if replay.id != asset_id:
            msg = "Asset operation identity already binds another asset"
            raise ConflictError(msg)
        return replay
    before = _current(session, asset_id, context)
    if status == "draft":
        msg = "Published assets cannot return to draft"
        raise ValidationError(msg)
    validate_asset_target(session, before.definition)
    asset = before.model_copy(
        update={
            "revision": before.revision + 1,
            "status": status,
            "updated_at": utcnow(),
        }
    )
    return _record(session, asset, context, status)


def asset_history(db: Database, asset_id: str) -> tuple[AssetHistory, ...]:
    """Read all revisions ordered by their revision number."""
    with db.session() as session:
        asset_in_session(session, asset_id)
        entries = [
            AssetHistory.model_validate(row.payload)
            for row in session.scalars(
                select(DataAssetHistoryRow).where(DataAssetHistoryRow.asset_id == asset_id)
            )
        ]
        return tuple(sorted(entries, key=lambda item: item.asset.revision))
