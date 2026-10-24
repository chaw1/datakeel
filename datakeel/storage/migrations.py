# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conservative schema additions within the caller's serialized migration transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import DDL, inspect
from sqlalchemy.schema import CreateColumn

from datakeel.core.errors import ValidationError
from datakeel.storage.base import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


def add_nullable_columns(connection: Connection) -> None:
    """Append missing nullable model columns without changing existing data or types."""
    inspector = inspect(connection)
    missing = [
        (table, column)
        for table in Base.metadata.sorted_tables
        for existing in [{item["name"] for item in inspector.get_columns(table.name)}]
        for column in table.columns
        if column.name not in existing
    ]
    for table, column in missing:
        if not column.nullable:
            msg = (
                f"Cannot add non-nullable column {table.name}.{column.name}: "
                "additive migration cannot infer values for existing rows"
            )
            raise ValidationError(msg)
    preparer = connection.dialect.identifier_preparer
    for table, column in missing:
        definition = CreateColumn(column).compile(dialect=connection.dialect)
        connection.execute(
            DDL(f"ALTER TABLE {preparer.format_table(table)} ADD COLUMN {definition}")
        )
    for table, _ in missing:
        for index in table.indexes:
            index.create(connection, checkfirst=True)
