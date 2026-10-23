# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real reflection, type inference, and SQL-derived provenance checks."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import SQLAlchemyError

from datakeel.catalog.importers import database as importer
from datakeel.catalog.importers.base import CatalogImporter
from datakeel.catalog.importers.database import reflect_database
from datakeel.catalog.importers.models import ImportBatch, SqlDefinition
from datakeel.catalog.importers.sql import derive_sql
from datakeel.catalog.service import import_catalog, prepare_import
from datakeel.core.catalog_models import (
    CatalogImportRequest,
    CatalogQuery,
    TableProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.storage.catalog_queries import read_objects

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_reflect_database_when_local_source_preserves_keys_and_view_fields(
    source_request: CatalogImportRequest,
) -> None:
    """Reflect keys and derive actual field dependencies through joins and a CTE."""
    snapshot, report = prepare_import(source_request)
    table = next(
        item for item in snapshot.objects if item.asset_ref.asset_id == "sample/main/sales"
    )
    properties = TableProperties.model_validate(table.properties.root)
    assert properties.primary_key == ("id",)
    assert properties.foreign_keys[0].target_table == "sample/main/regions"
    assert report.failed_sql_count == 0
    derived = {
        (link.source.asset_id, link.target.asset_id)
        for link in snapshot.links
        if link.kind == "derived"
    }
    assert ("sample/main/sales/amount", "sample/main/sales_view/doubled") in derived
    assert ("sample/main/regions/name", "sample/main/sales_view/name") in derived
    assert ("sample/main/sales/amount", "sample/main/daily/total") in derived
    assert len(derived) == 5


def test_import_sql_files_when_valid_and_broken_records_partial_success(
    db: Database, source_request: CatalogImportRequest, tmp_path: Path
) -> None:
    """Parse a supplied SQL output and report malformed input instead of fabricated edges."""
    good = tmp_path / "provided.sql"
    good.write_text(
        "CREATE VIEW computed AS SELECT id, amount + 3 AS total FROM sales", encoding="utf-8"
    )
    bad = tmp_path / "broken.sql"
    bad.write_text("SELECT ((", encoding="utf-8")
    report = import_catalog(
        db, source_request.model_copy(update={"sql_files": (str(good), str(bad))})
    )
    assert report.failed_sql_count == 1
    assert report.model_dump()["failed_sql_count"] == 1
    assert report.parse_failures[0].origin.startswith(str(bad))
    assert read_objects(db, CatalogQuery(kind="table", search="computed")).total == 1


@pytest.mark.parametrize(
    "query", ["DELETE FROM sales", "SELECT missing FROM sales", "SELECT missing FROM unknown"]
)
def test_derive_sql_when_write_or_unknown_field_records_failure(
    source_request: CatalogImportRequest, query: str
) -> None:
    """Reject SQL that cannot prove registered input field provenance."""
    batch = reflect_database(source_request)
    result = derive_sql(
        batch.snapshot, (SqlDefinition(origin="test", table_id="sample/main/result", sql=query),)
    )
    assert len(result.failures) == 1


def test_reflect_when_missing_url_or_path_fails_without_creating_database(tmp_path: Path) -> None:
    """Metadata inspection never creates the requested SQLite source."""
    request = CatalogImportRequest(source_id="missing", name="Missing")
    with pytest.raises(ValidationError, match="requires"):
        prepare_import(request)
    with pytest.raises(ValidationError, match="requires"):
        reflect_database(request)
    missing = tmp_path / "absent.db"
    with pytest.raises(ValidationError, match="does not exist"):
        reflect_database(request.model_copy(update={"connection_url": f"sqlite:///{missing}"}))
    assert not missing.exists()


def test_reflect_when_driver_failure_wraps_without_leaking_url(
    source_request: CatalogImportRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expose a domain failure while disposing the source engine."""

    def fail(*_args: object) -> object:
        msg = "private connection details"
        raise SQLAlchemyError(msg)

    monkeypatch.setattr(importer, "inspect", fail)
    with pytest.raises(ValidationError, match="Source reflection failed: SQLAlchemyError"):
        reflect_database(source_request)


def test_reflect_when_non_sqlite_url_rejects_before_connecting() -> None:
    """The narrowed P4 adapter declines other dialects without any connection attempt."""
    with pytest.raises(ValidationError, match="only SQLite"):
        reflect_database(
            CatalogImportRequest(
                source_id="sample", name="Sample", connection_url="postgresql://localhost/unused"
            )
        )


def test_sql_when_multiple_statements_keep_valid_after_each_failure(
    source_request: CatalogImportRequest,
) -> None:
    """Report each failed statement and continue to valid definitions in the same file."""
    batch = reflect_database(source_request)
    definition = SqlDefinition(
        origin="batch.sql",
        table_id="sample/main/result",
        sql=(
            "DELETE FROM sales; CREATE VIEW second AS SELECT id FROM sales; "
            "UPDATE sales SET amount=3; CREATE VIEW third AS SELECT amount FROM sales"
        ),
    )
    result = derive_sql(batch.snapshot, (definition,))
    assert len(result.failures) == 2
    assert {item.asset_ref.asset_id for item in result.snapshot.objects} >= {
        "sample/main/second/id",
        "sample/main/third/amount",
    }


def test_reflect_when_special_names_percent_encodes_each_identity(tmp_path: Path) -> None:
    """Preserve mixed case and escape slashes, percent signs, and spaces per segment."""
    path = tmp_path / "names.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            'CREATE TABLE "Mixed /%" ("Amount /%" REAL); '
            'CREATE VIEW "View /%" AS SELECT "Amount /%" FROM "Mixed /%";'
        )
    snapshot, report = prepare_import(
        CatalogImportRequest(
            source_id="Source /%", name="Names", connection_url=f"sqlite:///{path}"
        )
    )
    assert report.failed_sql_count == 0
    assert any(
        item.asset_ref.asset_id == "Source%20%2F%25/main/Mixed%20%2F%25/Amount%20%2F%25"
        for item in snapshot.objects
    )
    assert any(link.kind == "derived" for link in snapshot.links)


def test_reflection_when_foreign_key_emits_reference_without_derivation(
    source_request: CatalogImportRequest,
) -> None:
    """Foreign keys remain references; only the SQL parser may produce derived links."""
    batch = reflect_database(source_request)
    assert not any(link.kind == "derived" for link in batch.snapshot.links)
    references = [link for link in batch.snapshot.links if link.kind == "references"]
    assert len(references) == 1
    assert references[0].source.asset_id == "sample/main/sales/region_id"
    assert references[0].target.asset_id == "sample/main/regions/id"


def test_sql_when_syntax_failure_precedes_valid_statement_continues(
    source_request: CatalogImportRequest,
) -> None:
    """Tokenize statement boundaries without splitting quoted literal semicolons."""
    batch = reflect_database(source_request)
    result = derive_sql(
        batch.snapshot,
        (
            SqlDefinition(
                origin="mixed.sql",
                table_id="sample/main/result",
                sql="SELECT ((; CREATE VIEW valid AS SELECT id, 'a;b' AS label FROM sales;",
            ),
        ),
    )
    assert len(result.failures) == 1
    assert any(
        item.asset_ref.asset_id == "sample/main/valid/id" for item in result.snapshot.objects
    )


def test_importer_interface_when_custom_adapter_returns_typed_batch(
    source_request: CatalogImportRequest,
) -> None:
    """Keep future file importers behind the same typed extension interface."""

    class LocalAdapter(CatalogImporter):
        def reflect(self, request: CatalogImportRequest) -> ImportBatch:
            return reflect_database(request)

    assert LocalAdapter().reflect(source_request).snapshot.objects
