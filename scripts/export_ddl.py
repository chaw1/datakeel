# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export deterministic, complete live SQLite/PostgreSQL schema facts without migration."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

from datakeel.core.models import BoundaryModel

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


class DDLRecord(BoundaryModel):
    """Keep a named catalog fact and its lossless JSON representation."""

    category: str
    name: str
    definition: str


class DDLSnapshot(BoundaryModel):
    """Include database version and every normalized schema fact."""

    dialect: str
    version: str
    records: tuple[DDLRecord, ...]


def _record(category: str, name: str, definition: object) -> DDLRecord:
    return DDLRecord(
        category=category,
        name=name,
        definition=json.dumps(definition, sort_keys=True, ensure_ascii=False, default=str),
    )


def _sqlite_catalog(connection: Connection) -> list[DDLRecord]:
    records = [
        _record(str(row.type), str(row.name), tuple(row))
        for row in connection.execute(
            text("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name")
        )
    ]
    for table in inspect(connection).get_table_names():
        quoted = connection.dialect.identifier_preparer.quote(table)
        records.extend(
            _record(
                pragma,
                table,
                [tuple(row) for row in connection.exec_driver_sql(f"PRAGMA {pragma}({quoted})")],
            )
            for pragma in ("table_xinfo", "foreign_key_list", "index_list")
        )
    return records


def _postgres_catalog(connection: Connection) -> list[DDLRecord]:
    queries = {
        "constraint": """SELECT c.relname || '.' || k.conname,
            pg_get_constraintdef(k.oid, true) FROM pg_constraint k
            JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema()""",
        "index": """SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname=current_schema()""",
        "trigger": """SELECT c.relname || '.' || t.tgname, pg_get_triggerdef(t.oid, true)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND NOT t.tgisinternal""",
        "function": """SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid)
            || ')', pg_get_functiondef(p.oid) FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=current_schema() AND p.prokind IN ('f', 'p')""",
        "sequence": """SELECT sequencename, to_jsonb(s) - 'schemaname' FROM pg_sequences s
            WHERE schemaname=current_schema()""",
        "view": """SELECT viewname, definition FROM pg_views
            WHERE schemaname=current_schema()""",
    }
    return [
        _record(category, str(row[0]), row[1])
        for category, query in queries.items()
        for row in connection.execute(text(query))
    ]


def snapshot(connection: Connection) -> DDLSnapshot:
    """Read full column, key, constraint, index, trigger and function definitions."""
    inspector = inspect(connection)
    records: list[DDLRecord] = []
    for table in sorted(inspector.get_table_names()):
        records.append(_record("columns", table, inspector.get_columns(table)))
        records.append(_record("primary_key", table, inspector.get_pk_constraint(table)))
        records.append(_record("foreign_keys", table, inspector.get_foreign_keys(table)))
        records.append(_record("unique", table, inspector.get_unique_constraints(table)))
        records.append(_record("checks", table, inspector.get_check_constraints(table)))
        records.append(_record("indexes", table, inspector.get_indexes(table)))
    sqlite = connection.dialect.name == "sqlite"
    records.extend(_sqlite_catalog(connection) if sqlite else _postgres_catalog(connection))
    version = connection.scalar(
        text("SELECT sqlite_version()" if sqlite else "SHOW server_version")
    )
    return DDLSnapshot(
        dialect=connection.dialect.name,
        version=str(version),
        records=tuple(sorted(records, key=lambda item: (item.category, item.name))),
    )


def main() -> None:
    """Read an explicitly selected existing database; never initialize its schema."""
    from datakeel.storage.database import Database  # noqa: PLC0415  # CLI-only engine setup.

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    args = parser.parse_args()
    database = Database(args.url, read_only=True)
    try:
        with database.engine.connect() as connection:
            result = snapshot(connection)
        from rich.console import Console  # noqa: PLC0415  # CLI output only.

        Console(soft_wrap=True).print(
            result.model_dump_json(indent=2), markup=False, highlight=False
        )
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
