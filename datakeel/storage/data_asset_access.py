# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One grant policy shared by all native reading entrances and immutable usage."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import (
    AccessContext,
    AssetGrant,
    AssetUsage,
    AssetUsageQuery,
    DataAsset,
    SkippedEntries,
)
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef, new_id, utcnow
from datakeel.storage.data_asset_rows import AssetGrantRow, AssetUsageRow
from datakeel.storage.data_asset_store import assets_in_session
from datakeel.storage.data_asset_targets import (
    resolve_access_targets,
    same_resource,
    target_index,
)
from datakeel.storage.database import Database


def matching_assets(session: Session, refs: tuple[AssetRef, ...]) -> tuple[DataAsset, ...]:
    """Match every policy on an accessed resource, including withdrawn protected assets."""
    if not refs:
        return ()
    policies = tuple(asset for asset in assets_in_session(session) if asset.status != "draft")
    if not policies:
        return ()
    expanded = resolve_access_targets(session, refs)
    return tuple(
        asset
        for asset in policies
        if any(same_resource(asset.definition.target, target) for target in expanded)
    )


def valid_grant(
    grants: tuple[AssetGrant, ...],
    asset_id: str,
    context: AccessContext,
    now: datetime,
) -> AssetGrant | None:
    """Require exact subject and scope, unrevoked state, and strictly future expiry."""
    return next(
        (
            grant
            for grant in grants
            if (
                grant.asset_id == asset_id
                and grant.subject == context.actor
                and context.scope in grant.scopes
                and grant.revoked_at is None
                and grant.created_at <= now < grant.expires_at
            )
        ),
        None,
    )


def require_access_in_session(
    session: Session,
    refs: tuple[AssetRef, ...],
    context: AccessContext,
    *,
    now: datetime | None = None,
    record: bool = True,
) -> tuple[AssetUsage, ...]:
    """Reject all data reads unless every matched restricted policy authorizes them.

    The caller owns the transaction. All policies are checked before any usage is
    appended, so a rejected multi-resource read never emits a successful usage.
    """
    moment = now or utcnow()
    assets = matching_assets(session, refs)
    if not assets:
        return ()
    grants = _actor_grants(session, context.actor)
    usages: list[AssetUsage] = []
    for asset in assets:
        grant = valid_grant(grants, asset.id, context, moment)
        if asset.definition.classification in {"request", "restricted"} and grant is None:
            msg = f"Asset {asset.id} requires an active {context.scope} grant; apply for access"
            raise AuthorizationError(msg)
        usages.append(
            AssetUsage(
                id=new_id(),
                asset_id=asset.id,
                actor=context.actor,
                entry=context.entry,
                scope=context.scope,
                occurred_at=moment,
                grant_id=grant.id if grant else None,
            )
        )
    if record:
        for usage in usages:
            session.add(
                AssetUsageRow(
                    id=usage.id,
                    asset_id=usage.asset_id,
                    actor=usage.actor,
                    occurred_at=moment.timestamp(),
                    payload=usage.model_dump(mode="json"),
                )
            )
        session.flush()
    return tuple(usages) if record else ()


def _actor_grants(session: Session, actor: str) -> tuple[AssetGrant, ...]:
    return tuple(
        AssetGrant.model_validate(row.payload)
        for row in session.scalars(
            select(AssetGrantRow).where(AssetGrantRow.subject == actor).order_by(AssetGrantRow.id)
        )
    )


def skip_protected_in_session(
    session: Session,
    entries: Sequence[tuple[str, tuple[AssetRef, ...]]],
    context: AccessContext,
    *,
    now: datetime | None = None,
) -> SkippedEntries | None:
    """Name the entries of a list-style read that the caller may not read, by ID only.

    Each entry is checked with the same policy as a single read; callers drop the
    reported entries and authorize the rest, so one protected entry no longer fails
    the whole listing.
    """
    moment = now or utcnow()
    grants = _actor_grants(session, context.actor)
    guarded = tuple(
        asset
        for asset in assets_in_session(session)
        if asset.status != "draft"
        and asset.definition.classification in {"request", "restricted"}
        and valid_grant(grants, asset.id, context, moment) is None
    )
    if not guarded or not entries:
        return None
    index = target_index(session)
    skipped: dict[str, None] = {}
    blocking: dict[str, None] = {}
    for identifier, refs in entries:
        expanded = resolve_access_targets(session, refs, index) if refs else ()
        matched = [
            asset.id
            for asset in guarded
            if any(same_resource(asset.definition.target, target) for target in expanded)
        ]
        if matched:
            skipped[identifier] = None
            blocking.update(dict.fromkeys(matched))
    if not skipped:
        return None
    return SkippedEntries(
        count=len(skipped),
        ids=list(skipped),
        assets=sorted(blocking),
        reason=(
            f"Protected data assets require an active {context.scope} grant for this "
            "operator; apply for access to include these entries"
        ),
    )


def skip_protected(
    db: Database,
    entries: Sequence[tuple[str, tuple[AssetRef, ...]]],
    context: AccessContext,
) -> SkippedEntries | None:
    """Check a list-style read in one transaction; see skip_protected_in_session."""
    with db.session() as session:
        return skip_protected_in_session(session, entries, context)


def require_access(
    db: Database,
    refs: tuple[AssetRef, ...],
    context: AccessContext,
    *,
    now: datetime | None = None,
    record: bool = True,
) -> tuple[AssetUsage, ...]:
    """Check a native read and append exactly one usage per matching asset."""
    with db.session() as session:
        if record:
            db.lock_writes(session)
        result = require_access_in_session(session, refs, context, now=now, record=record)
        session.commit()
        return result


def list_usage(db: Database, query: AssetUsageQuery) -> tuple[AssetUsage, ...]:
    """Read successful uses by asset and/or actor, newest first with stable ties."""
    with db.session() as session:
        statement = select(AssetUsageRow)
        if query.asset_id is not None:
            statement = statement.where(AssetUsageRow.asset_id == query.asset_id)
        if query.actor is not None:
            statement = statement.where(AssetUsageRow.actor == query.actor)
        statement = statement.order_by(AssetUsageRow.occurred_at.desc(), AssetUsageRow.id)
        return tuple(
            AssetUsage.model_validate(row.payload)
            for row in session.scalars(statement.limit(query.limit))
        )
