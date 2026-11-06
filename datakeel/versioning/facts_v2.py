# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify additive migrations preserve every old field, row identity and blob byte."""

import hashlib
import json

from sqlalchemy.engine import Connection

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.versioning.inspect import quote, schema_objects


class TableFacts(BoundaryModel):
    """Freeze a projection of the pre-migration fields and SQLite row identities."""

    name: str
    columns: tuple[str, ...]
    digest: str


def _blob(value: object) -> dict[str, str]:
    if not isinstance(value, bytes):
        msg = "Unexpected SQLite fact type"
        raise ValidationError(msg)
    return {"sqlite_blob_hex": value.hex()}


def _digest(connection: Connection, name: str, columns: tuple[str, ...]) -> str:
    projection = ",".join(("rowid", *(quote(column) for column in columns)))
    rows = connection.exec_driver_sql(f"SELECT {projection} FROM {quote(name)}")  # noqa: S608
    encoded = sorted(json.dumps(tuple(row), default=_blob) for row in rows)
    return hashlib.sha256(json.dumps(encoded).encode()).hexdigest()


def snapshot(connection: Connection) -> tuple[TableFacts, ...]:
    """Capture old fields without treating new empty tables or NULL columns as changed facts."""
    result: list[TableFacts] = []
    for item in schema_objects(connection):
        if item.kind == "table":
            columns = tuple(
                str(row[1])
                for row in connection.exec_driver_sql(f"PRAGMA table_info({quote(item.name)})")
            )
            result.append(
                TableFacts(
                    name=item.name, columns=columns, digest=_digest(connection, item.name, columns)
                )
            )
    return tuple(result)


def validate_preserved(connection: Connection, before: tuple[TableFacts, ...]) -> None:
    """Reject changed old rows, non-NULL added fields and populated new tables."""
    previous = {table.name: table for table in before}
    for current in snapshot(connection):
        old = previous.get(current.name)
        if old is None:
            changed = (
                connection.exec_driver_sql(
                    f"SELECT 1 FROM {quote(current.name)} LIMIT 1"  # noqa: S608
                ).fetchone()
                is not None
            )
        else:
            changed = _digest(connection, old.name, old.columns) != old.digest
            for column in set(current.columns) - set(old.columns):
                changed |= (
                    connection.exec_driver_sql(
                        f"SELECT 1 FROM {quote(current.name)} "  # noqa: S608
                        f"WHERE {quote(column)} IS NOT NULL LIMIT 1"
                    ).fetchone()
                    is not None
                )
        if changed:
            msg = "Unauthorized business fact changes"
            raise ValidationError(msg)
    if previous.keys() - {table.name for table in snapshot(connection)}:
        msg = "Unauthorized business table removal"
        raise ValidationError(msg)
