# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Select bounded catalog pages before validating rich object payloads."""

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogObject, CatalogPage, CatalogQuery
from datakeel.storage.catalog_fields import read_fields
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow


def _filtered(query: CatalogQuery) -> Select[CatalogObjectRow]:
    statement = select(CatalogObjectRow)
    if query.kind is not None:
        statement = statement.where(CatalogObjectRow.kind == query.kind)
    if query.parent_id is not None:
        statement = statement.where(
            CatalogObjectRow.asset_id.in_(
                select(CatalogEdgeRow.target_id).where(
                    CatalogEdgeRow.kind == "contains",
                    CatalogEdgeRow.source_id == query.parent_id,
                )
            )
        )
    return statement.order_by(CatalogObjectRow.kind, CatalogObjectRow.asset_id)


def _search_ids(session: Session, query: CatalogQuery) -> tuple[list[str], int]:
    # Python source equality and Unicode casefold run before page selection.
    needle = (query.search or "").casefold()
    identities: list[str] = []
    total = 0
    for item in read_fields(session, _filtered(query)):
        if query.source_id is not None and item.source_id != query.source_id:
            continue
        if needle in item.name.casefold() or needle in (item.english_name or "").casefold():
            if query.offset <= total < query.offset + query.limit:
                identities.append(item.identity)
            total += 1
    return identities, total


def read_page(session: Session, query: CatalogQuery) -> CatalogPage:
    """Apply filters before loading payloads while preserving stable Unicode search."""
    statement = _filtered(query)
    if query.search is None and query.source_id is None:
        total = session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = session.scalars(statement.offset(query.offset).limit(query.limit))
    else:
        identities, total = _search_ids(session, query)
        rows = session.scalars(
            select(CatalogObjectRow)
            .where(CatalogObjectRow.asset_id.in_(identities))
            .order_by(CatalogObjectRow.kind, CatalogObjectRow.asset_id)
        )
    return CatalogPage(
        items=tuple(CatalogObject.model_validate(row.payload) for row in rows),
        total=total or 0,
        offset=query.offset,
        limit=query.limit,
    )
