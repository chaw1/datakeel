# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured asset cards projected from native datasets, lineage and usage facts."""

from collections import deque
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.data_asset_models import DataAsset, DataAssetCard
from datakeel.core.models import AssetRef, LineageEvent, utcnow
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.data_asset_events import data_dependency_events
from datakeel.storage.data_asset_quality import asset_quality
from datakeel.storage.data_asset_rows import AssetUsageRow
from datakeel.storage.data_asset_store import asset_in_session, assets_in_session
from datakeel.storage.data_asset_targets import ref_key, resolve_access_targets, same_resource
from datakeel.storage.database import Database, DatasetRow, VersionRow

type EdgeIndex = dict[str, list[tuple[AssetRef, AssetRef]]]


def _graph(
    snapshot: CatalogSnapshot,
    events: list[LineageEvent],
) -> tuple[EdgeIndex, EdgeIndex]:
    upstream: EdgeIndex = {}
    downstream: EdgeIndex = {}
    pairs: list[tuple[AssetRef, AssetRef]] = []
    for event in events:
        if event.run_state == "COMPLETED":
            pairs.extend((source, target) for source in event.inputs for target in event.outputs)
    for link in snapshot.links:
        if link.kind in {"contains", "derived"}:
            pairs.append((link.source, link.target))
        elif link.kind in {"measures", "sliced_by", "means"}:
            pairs.append((link.target, link.source))
    for source, target in pairs:
        upstream.setdefault(target.asset_id, []).append((target, source))
        downstream.setdefault(source.asset_id, []).append((source, target))
    return upstream, downstream


def _walk(target: AssetRef, edges: EdgeIndex) -> tuple[AssetRef, ...]:
    queue = deque(
        neighbor
        for origin, neighbor in edges.get(target.asset_id, ())
        if same_resource(origin, target)
    )
    found: dict[tuple[str, str, str, str | None], AssetRef] = {}
    while queue:
        ref = queue.popleft()
        if same_resource(target, ref) or ref_key(ref) in found:
            continue
        found[ref_key(ref)] = ref
        queue.extend(
            neighbor
            for origin, neighbor in edges.get(ref.asset_id, ())
            if same_resource(origin, ref)
        )
    return tuple(found[key] for key in sorted(found, key=str))


def _updated(session: Session, target: AssetRef, events: list[LineageEvent]) -> datetime | None:
    times = [
        event.occurred_at
        for event in events
        if event.run_state == "COMPLETED"
        and any(same_resource(target, output) for output in event.outputs)
    ]
    if target.asset_type == "dataset":
        statement = select(VersionRow).where(VersionRow.dataset_id == target.asset_id)
        if target.version:
            statement = statement.where(VersionRow.id == target.version)
        times.extend(
            datetime.fromtimestamp(row.created_at, UTC) for row in session.scalars(statement)
        )
        row = session.get(DatasetRow, target.asset_id)
        if row:
            times.append(datetime.fromtimestamp(row.created_at, UTC))
    if target.asset_type in {"table", "metric"}:
        catalog = read_snapshot(session)
        producers = {
            item.producer_event_id
            for item in catalog.objects
            if same_resource(target, item.asset_ref)
        }
        times.extend(event.occurred_at for event in events if event.event_id in producers)
        for ref in resolve_access_targets(session, (target,)):
            if ref.asset_type == "dataset":
                observed = _updated(session, ref, events)
                if observed is not None:
                    times.append(observed)
    return max(times) if times else None


def card_in_session(
    session: Session,
    asset: DataAsset,
    now: datetime,
) -> DataAssetCard:
    """Compute factual card values in a consistent native database snapshot."""
    target = asset.definition.target
    events = data_dependency_events(session)
    snapshot = read_snapshot(session)
    upstream_edges, downstream_edges = _graph(snapshot, events)
    upstream = _walk(target, upstream_edges)
    downstream = _walk(target, downstream_edges)
    quality, trend = asset_quality(session, target)
    updated = _updated(session, target, events)
    usages = list(session.scalars(select(AssetUsageRow).where(AssetUsageRow.asset_id == asset.id)))
    related_ids = {ref.asset_id for ref in (*upstream, *downstream, target)}
    metrics = tuple(
        item.asset_ref
        for item in snapshot.objects
        if (
            item.asset_ref.asset_type == "metric"
            and (item.asset_ref.asset_id in related_ids or item.table_id in related_ids)
        )
    )
    return DataAssetCard(
        asset=asset,
        quality_score=quality,
        quality_trend=trend,
        upstream=upstream,
        downstream=downstream,
        updated_at=updated,
        related_metrics=metrics,
        usage_count=len(usages),
        user_count=len({row.actor for row in usages}),
        downstream_count=len(downstream),
        freshness_seconds=max(0, (now - updated).total_seconds()) if updated else None,
    )


def get_asset_card(db: Database, asset_id: str, *, now: datetime | None = None) -> DataAssetCard:
    """Return one business card with live factual aggregates and optional extension slots."""
    with db.session() as session:
        return card_in_session(session, asset_in_session(session, asset_id), now or utcnow())


def all_asset_cards(db: Database, *, now: datetime | None = None) -> tuple[DataAssetCard, ...]:
    """Project all cards for local, deterministic market search and ranking."""
    with db.session() as session:
        moment = now or utcnow()
        return tuple(
            card_in_session(session, asset, moment) for asset in assets_in_session(session)
        )


__all__ = ["all_asset_cards", "get_asset_card"]
