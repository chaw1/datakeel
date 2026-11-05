# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enumerate local object references from the actual recovery snapshot."""

import json

from pydantic import JsonValue, TypeAdapter
from sqlalchemy.engine import Connection

from datakeel.core.errors import ValidationError
from datakeel.versioning.inspect import quote, schema_objects

REFERENCE_FIELDS = frozenset({"object_key", "ledger_key"})


def _nested(value: JsonValue) -> set[str]:
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_nested(item))
        return keys
    if not isinstance(value, dict):
        return set()
    keys: set[str] = set()
    for key, item in value.items():
        if key in REFERENCE_FIELDS and item is not None:
            if not isinstance(item, str) or not item:
                msg = "Invalid object reference"
                raise ValidationError(msg)
            keys.add(item)
        keys.update(_nested(item))
    return keys


def referenced_objects(connection: Connection) -> tuple[str, ...]:
    """Inspect every JSON value and every dedicated object-key column, including history."""
    result: set[str] = set()
    for table in schema_objects(connection):
        if table.kind != "table":
            continue
        columns = connection.exec_driver_sql(f"PRAGMA table_info({quote(table.name)})").fetchall()
        for column in columns:
            name, datatype = str(column[1]), str(column[2]).upper()
            if name not in REFERENCE_FIELDS and datatype != "JSON":
                continue
            for row in connection.exec_driver_sql(
                f"SELECT {quote(name)} FROM {quote(table.name)} WHERE {quote(name)} IS NOT NULL"  # noqa: S608  # Identifiers are double-quoted and escaped.
            ):
                if name in REFERENCE_FIELDS:
                    result.add(str(row[0]))
                else:
                    value = TypeAdapter(JsonValue).validate_python(json.loads(row[0]))
                    result.update(_nested(value))
    return tuple(sorted(result))
