# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assemble table detail without exposing persistence rows or unbounded graph data."""

from datakeel.core.catalog_models import CatalogTableDetail, ImpactResult
from datakeel.core.errors import NotFoundError
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.database import Database


def table_detail(db: Database, asset_id: str) -> CatalogTableDetail:
    """Read fields, consuming metrics, and direct owners from one consistent snapshot."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    table = next(
        (
            item
            for item in snapshot.objects
            if item.asset_ref.asset_id == asset_id and item.asset_ref.asset_type == "table"
        ),
        None,
    )
    if table is None:
        msg = f"Catalog table not found: {asset_id}"
        raise NotFoundError(msg)
    columns = tuple(
        item
        for item in snapshot.objects
        if item.table_id == asset_id and item.asset_ref.asset_type == "column"
    )
    column_ids = {item.asset_ref.asset_id for item in columns}
    metric_ids = {
        link.source.asset_id
        for link in snapshot.links
        if link.kind == "measures" and link.target.asset_id in column_ids
    }
    metrics = tuple(item for item in snapshot.objects if item.asset_ref.asset_id in metric_ids)
    owner_ids = {
        link.target.asset_id
        for link in snapshot.links
        if link.kind == "owned_by" and link.source.asset_id in {asset_id, *metric_ids}
    }
    links = tuple(
        link
        for link in snapshot.links
        if asset_id in {link.source.asset_id, link.target.asset_id}
        or link.source.asset_id in column_ids
        or link.target.asset_id in column_ids
    )
    related = {ref.asset_id for link in links for ref in (link.source, link.target)}
    return CatalogTableDetail(
        table=table,
        columns=columns,
        metrics=metrics,
        owners=tuple(item for item in snapshot.objects if item.asset_ref.asset_id in owner_ids),
        neighbors=ImpactResult(
            asset_id=asset_id,
            links=links,
            objects=tuple(item for item in snapshot.objects if item.asset_ref.asset_id in related),
        ),
    )
