# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Orchestrate source adapters and publish a reversible metadata snapshot."""

from pathlib import Path

from datakeel.catalog.importers.database import reflect_database
from datakeel.catalog.importers.models import SqlDefinition
from datakeel.catalog.importers.sql import derive_sql
from datakeel.catalog.importers.tabular import reflect_files
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import CatalogImportRequest, CatalogSnapshot, ImportReport
from datakeel.core.errors import ValidationError
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database


def prepare_import(request: CatalogImportRequest) -> tuple[CatalogSnapshot, ImportReport]:
    """Read source metadata before opening the authoritative store transaction."""
    if request.files and request.connection_url:
        msg = "Catalog import requires either files or a SQLite URL, not both"
        raise ValidationError(msg)
    if not request.files and not request.connection_url:
        msg = "Catalog import requires files or a SQLite URL"
        raise ValidationError(msg)
    batch = reflect_files(request) if request.files else reflect_database(request)
    snapshot, definitions = batch.snapshot, batch.sql
    definitions += tuple(
        SqlDefinition(
            origin=filename,
            table_id=catalog_id(request.source_id, "main", Path(filename).stem),
            sql=Path(filename).read_text(encoding="utf-8"),
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
