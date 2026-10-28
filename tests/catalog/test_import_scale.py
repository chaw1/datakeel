# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Large dbt projects import in linear work: bounded parser schemas, few write statements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import event

from datakeel.catalog.importers import sql
from datakeel.catalog.importers.dbt import prepare_dbt
from datakeel.catalog.metadata_service import import_dbt
from datakeel.core.metadata_imports import DbtImportRequest
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_reads import read_snapshot

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.engine import Connection
    from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext

    from datakeel.storage.database import Database

MODELS = 150
COLUMNS = ("c0", "c1", "c2")


def _chain(count: int = MODELS) -> DbtImportRequest:
    """Each model selects every column of the previous one, like a long staging chain."""
    nodes: dict[str, object] = {}
    reflected: dict[str, object] = {}
    literals = ", ".join(f"{index} as {name}" for index, name in enumerate(COLUMNS))
    for index in range(count):
        parent = f"model.big.m{index - 1}" if index else None
        origin = f'"big"."main"."m{index - 1}"' if parent else f"(select {literals}) seed"
        nodes[f"model.big.m{index}"] = {
            "unique_id": f"model.big.m{index}",
            "name": f"m{index}",
            "resource_type": "model",
            "database": "big",
            "schema": "main",
            "relation_name": f'"big"."main"."m{index}"',
            "config": {"materialized": "table"},
            "columns": {name: {"name": name} for name in COLUMNS},
            "depends_on": {"nodes": [parent] if parent else []},
            "compiled_code": f"select {', '.join(COLUMNS)} from {origin}",  # noqa: S608  # Fixture SQL.
        }
        reflected[f"model.big.m{index}"] = {
            "metadata": {"type": "BASE TABLE"},
            "columns": {
                name: {"name": name, "type": "INTEGER", "index": position}
                for position, name in enumerate(COLUMNS)
            },
        }
    manifest = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
            "adapter_type": "duckdb",
        },
        "nodes": nodes,
        "sources": {},
    }
    return DbtImportRequest(
        source_id="big",
        manifest=JsonDocument(manifest),
        catalog=JsonDocument({"nodes": reflected, "sources": {}}),
    )


def test_each_statement_is_parsed_against_only_the_tables_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handing sqlglot the whole catalog per statement made large projects quadratic."""
    sizes: list[int] = []
    derive = sql.lineage

    def recording(column: None, query: object, *, schema: sql.Schema, **options: object) -> object:
        sizes.append(sum(len(tables) for tables in schema.values()))
        return derive(column, query, schema=schema, **options)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(sql, "lineage", recording)
    batch = prepare_dbt(_chain())
    derived = [
        link
        for link in batch.snapshot.links
        if link.kind == "derived" and link.source.asset_type == "column"
    ]
    assert batch.parse_failures == ()
    assert len(sizes) == MODELS
    assert max(sizes) == 1
    assert len(derived) == (MODELS - 1) * len(COLUMNS)


def _count_writes(db: Database) -> list[int]:
    """Record catalog projection INSERT round trips; executemany costs one per row."""
    writes: list[int] = []

    @event.listens_for(db.engine, "before_cursor_execute")
    def _count(  # pyright: ignore[reportUnusedFunction]
        _connection: Connection,
        _cursor: DBAPICursor,
        statement: str,
        parameters: object,
        _context: ExecutionContext | None,
        executemany: bool,  # noqa: FBT001  # SQLAlchemy event signature.
    ) -> None:
        if (
            statement.lstrip()
            .upper()
            .startswith(("INSERT INTO CATALOG_OBJECTS", "INSERT INTO CATALOG_EDGES"))
        ):
            writes.append(len(parameters) if executemany and isinstance(parameters, list) else 1)

    return writes


def test_projection_reaches_the_database_in_a_few_statements(db: Database) -> None:
    """One INSERT per row is one server round trip each: 28 s for 1000 models on Postgres."""
    writes = _count_writes(db)
    report = import_dbt(db, _chain())
    with db.session() as session:
        current = read_snapshot(session)
    assert report.new == report.object_count == len(current.objects)
    assert len(current.links) > report.object_count
    assert sum(writes) <= 4


def test_projection_batches_respect_the_dialect_parameter_limit(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Statements split at the bound-parameter limit and still write every row once."""
    monkeypatch.setattr(db.engine.dialect, "insertmanyvalues_max_parameters", 70)
    writes = _count_writes(db)
    report = import_dbt(db, _chain(12))
    with db.session() as session:
        current = read_snapshot(session)
    objects = report.object_count
    edges = len(current.links)
    assert len(current.objects) == objects
    assert sum(writes) == -(-objects // (70 // 4)) + -(-edges // (70 // 7))
