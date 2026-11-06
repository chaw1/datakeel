# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""SQLite v2 recognition, retaining the frozen v1 ledger and validation contracts."""

import hashlib
import json
import re
from importlib.resources import files

from pydantic import TypeAdapter
from sqlalchemy.engine import Connection

from datakeel.core.errors import ValidationError
from datakeel.versioning.models import (
    BaselineDefinition,
    DatabaseStatus,
    LedgerRecord,
    MigrationDefinition,
    SchemaObject,
)

LEDGER = "datakeel_schema_versions"
LEDGER_SQL = (
    f"CREATE TABLE {LEDGER} (version INTEGER NOT NULL PRIMARY KEY, "
    "checksum TEXT NOT NULL, baseline TEXT NOT NULL, minimum_reader INTEGER NOT NULL, "
    "applied_at TEXT NOT NULL, campaign TEXT NOT NULL, facts TEXT NOT NULL)"
)
LEDGER_TRIGGERS = tuple(
    f"CREATE TRIGGER datakeel_ledger_no_{action.lower()} BEFORE {action} ON {LEDGER} "
    "BEGIN SELECT RAISE(ABORT, 'immutable migration ledger'); END"
    for action in ("UPDATE", "DELETE")
)


def normalize_sql(sql: str) -> str:
    """Normalize token whitespace while preserving every quoted SQL literal/identifier byte."""
    return " ".join(
        re.findall(
            r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^]]*\]|[^\s'\"`\[]+",
            sql,
        )
    )


def schema_objects(connection: Connection, *, system: bool = False) -> tuple[SchemaObject, ...]:
    """Read every user table, view, index and trigger, including unexpected objects."""
    rows = connection.exec_driver_sql(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name"
    )
    return tuple(
        SchemaObject(kind=row[0], name=row[1], table=row[2], sql=normalize_sql(row[3]))
        for row in rows
        if (row[2] == LEDGER) == system
    )


def quote(identifier: str) -> str:
    """Quote an SQLite identifier without permitting statement injection."""
    return '"' + identifier.replace('"', '""') + '"'


def validate_baseline(connection: Connection, baseline: BaselineDefinition) -> None:
    """Match complete DDL and legal data independently of row count or fixture hashes."""
    baseline = _physical_baseline(connection, baseline)
    expected = tuple(
        item.model_copy(update={"sql": normalize_sql(item.sql)}) for item in baseline.objects
    )
    if schema_objects(connection) != expected:
        msg = "Unknown or mixed schema; full baseline mismatch"
        raise ValidationError(msg)
    if connection.exec_driver_sql("PRAGMA integrity_check").fetchall() != [("ok",)]:
        msg = "Database integrity check failed"
        raise ValidationError(msg)
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone():
        msg = "Business foreign key invariant failed"
        raise ValidationError(msg)
    _validate_json(connection, baseline)
    for query in baseline.invariants:
        if connection.exec_driver_sql(query).fetchone():
            msg = "Business data invariant failed"
            raise ValidationError(msg)


def _physical_baseline(connection: Connection, baseline: BaselineDefinition) -> BaselineDefinition:
    # SQLite ADD COLUMN retains existing column order. Accept only the independently
    # frozen real ALTER result, never arbitrary reordered/extra columns or altered DDL.
    if baseline.id != "sqlite-b2":
        return baseline
    alternate = TypeAdapter(SchemaObject).validate_json(
        files("datakeel.versioning").joinpath("sqlite_b2_altered_shards.json").read_bytes()
    )
    actual = next(
        (item for item in schema_objects(connection) if item.name == alternate.name), None
    )
    if actual != alternate.model_copy(update={"sql": normalize_sql(alternate.sql)}):
        return baseline
    return baseline.model_copy(
        update={
            "objects": tuple(
                alternate if item.name == alternate.name else item for item in baseline.objects
            )
        }
    )


def _validate_json(connection: Connection, baseline: BaselineDefinition) -> None:
    for item in baseline.objects:
        if item.kind != "table":
            continue
        for column in connection.exec_driver_sql(f"PRAGMA table_info({quote(item.name)})"):
            if str(column[2]).upper() == "JSON":
                name = quote(column[1])
                if connection.exec_driver_sql(
                    f"SELECT 1 FROM {quote(item.name)} WHERE {name} IS NOT NULL "  # noqa: S608
                    f"AND NOT json_valid({name}) LIMIT 1"
                ).fetchone():
                    msg = "Invalid business JSON"
                    raise ValidationError(msg)


def _encode_blob(value: object) -> dict[str, str]:
    if not isinstance(value, bytes):
        msg = "Unexpected SQLite fact type"
        raise ValidationError(msg)
    return {"sqlite_blob_hex": value.hex()}


def facts_digest(connection: Connection) -> str:
    """Hash all business fields and row identities in deterministic table/row order."""
    digest = hashlib.sha256()
    for item in schema_objects(connection):
        if item.kind == "table":
            rows = connection.exec_driver_sql(f"SELECT * FROM {quote(item.name)}").fetchall()  # noqa: S608
            encoded = sorted(json.dumps(tuple(row), default=_encode_blob) for row in rows)
            digest.update(json.dumps([item.name, encoded]).encode())
    return digest.hexdigest()


def _ledger_objects() -> tuple[SchemaObject, ...]:
    return (
        SchemaObject(kind="table", name=LEDGER, table=LEDGER, sql=normalize_sql(LEDGER_SQL)),
        *(
            SchemaObject(
                kind="trigger",
                name=f"datakeel_ledger_no_{action}",
                table=LEDGER,
                sql=normalize_sql(sql),
            )
            for action, sql in zip(("delete", "update"), reversed(LEDGER_TRIGGERS), strict=True)
        ),
    )


def inspect_database(
    connection: Connection,
    versions: tuple[MigrationDefinition, ...],
    *,
    reader: int = 1,
) -> DatabaseStatus:
    """Accept only an exact baseline or a contiguous, verified registered prefix."""
    system = schema_objects(connection, system=True)
    if not system:
        return _unversioned(connection, versions)
    if system != _ledger_objects():
        msg = "Invalid ledger schema"
        raise ValidationError(msg)
    rows = connection.exec_driver_sql(
        "SELECT * FROM datakeel_schema_versions ORDER BY version"
    ).fetchall()
    if not rows or [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        msg = "Empty, duplicate or gapped ledger"
        raise ValidationError(msg)
    records = tuple(
        LedgerRecord.model_validate(dict(zip(LedgerRecord.model_fields, row, strict=True)))
        for row in rows
    )
    for record, definition in zip(records, versions, strict=False):
        if (record.version, record.checksum, record.baseline, record.minimum_reader) != (
            definition.version,
            definition.checksum,
            definition.target.id,
            definition.minimum_reader,
        ):
            msg = "Ledger checksum or metadata mismatch"
            raise ValidationError(msg)
    if len(rows) > len(versions):
        return DatabaseStatus(state="ahead", version=rows[-1][0], exit_code=6)
    latest = versions[len(rows) - 1]
    validate_baseline(connection, latest.target)
    pending = tuple(v.version for v in versions[len(rows) :])
    incompatible = reader < latest.minimum_reader
    return DatabaseStatus(
        state="ahead" if incompatible else "pending" if pending else "current",
        baseline=latest.target.id,
        version=latest.version,
        pending=pending,
        ledger_healthy=True,
        minimum_reader=latest.minimum_reader,
        exit_code=6 if incompatible else 0,
    )


def _unversioned(
    connection: Connection, versions: tuple[MigrationDefinition, ...]
) -> DatabaseStatus:
    objects = schema_objects(connection)
    if not objects:
        return DatabaseStatus(state="empty", pending=tuple(v.version for v in versions))
    for definition in reversed(versions):
        candidate = _physical_baseline(connection, definition.target)
        expected = tuple(
            item.model_copy(update={"sql": normalize_sql(item.sql)}) for item in candidate.objects
        )
        if objects == expected:
            validate_baseline(connection, definition.target)
            return DatabaseStatus(
                state="unversioned",
                baseline=definition.target.id,
                pending=tuple(v.version for v in versions),
            )
    msg = "Unknown or mixed schema; full baseline mismatch"
    raise ValidationError(msg)
