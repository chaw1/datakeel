# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate source adapters and publish a reversible metadata snapshot."""

from pathlib import Path

from datakeel.catalog.importers.database import reflect_database
from datakeel.catalog.importers.models import SqlDefinition
from datakeel.catalog.importers.sql import derive_sql
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import (
    CatalogImportRequest,
    CatalogSnapshot,
    ImportReport,
    SourceProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database


def prepare_import(request: CatalogImportRequest) -> tuple[CatalogSnapshot, ImportReport]:
    """Read source metadata before opening the authoritative store transaction."""
    if not request.connection_url or request.files:
        msg = "Catalog import requires a SQLite or PostgreSQL URL; file adapters are deferred"
        raise ValidationError(msg)
    batch = reflect_database(request)
    snapshot, definitions = batch.snapshot, batch.sql
    source = SourceProperties.model_validate(snapshot.objects[0].properties.root)
    dialect = "postgres" if source.dialect == "postgresql" else source.dialect
    schema = (
        request.schemas[0]
        if request.schemas
        else next(
            (item.schema_name for item in snapshot.objects if item.schema_name),
            "public" if dialect == "postgres" else "main",
        )
    )
    definitions += tuple(
        SqlDefinition(
            origin=filename,
            table_id=catalog_id(request.source_id, schema, Path(filename).stem),
            sql=Path(filename).read_text(encoding="utf-8"),
            dialect=dialect,
        )
        for filename in request.sql_files
    )
    result = derive_sql(snapshot, definitions)
    return result.snapshot, ImportReport(
        object_count=len(result.snapshot.objects), parse_failures=result.failures
    )


def import_catalog(
    db: Database, request: CatalogImportRequest, actor: str = "local-user"
) -> ImportReport:
    """Import one authorized metadata source, creating no event for unchanged content."""
    snapshot, parsed = prepare_import(request)
    report = publish_snapshot(db, snapshot, actor=actor)
    return report.model_copy(update={"parse_failures": parsed.parse_failures})
