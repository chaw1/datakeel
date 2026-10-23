# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed intermediate metadata and SQL inputs shared by import adapters."""

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.models import BoundaryModel


class SqlDefinition(BoundaryModel):
    """Bind a SQL definition to its output table and parser dialect."""

    origin: str
    table_id: str
    sql: str
    dialect: str = "sqlite"


class ImportBatch(BoundaryModel):
    """Carry reflected objects and unevaluated SQL definitions across adapters."""

    snapshot: CatalogSnapshot
    sql: tuple[SqlDefinition, ...] = ()
