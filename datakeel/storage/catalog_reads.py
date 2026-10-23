# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read current metadata projections through immutable boundary models."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow


def read_snapshot(session: Session) -> CatalogSnapshot:
    """Read the disposable current catalog in the caller's consistent transaction."""
    return CatalogSnapshot(
        scope="current",
        objects=tuple(
            CatalogObject.model_validate(row.payload)
            for row in session.scalars(
                select(CatalogObjectRow).order_by(CatalogObjectRow.kind, CatalogObjectRow.asset_id)
            )
        ),
        links=tuple(
            CatalogLink.model_validate(row.payload)
            for row in session.scalars(
                select(CatalogEdgeRow).order_by(
                    CatalogEdgeRow.kind, CatalogEdgeRow.source_id, CatalogEdgeRow.target_id
                )
            )
        ),
    )
