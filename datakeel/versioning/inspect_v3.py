# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""SQLite v3 recognition, retaining the frozen v1/v2 ledger and validation contracts."""

from importlib.resources import files

from pydantic import TypeAdapter
from sqlalchemy.engine import Connection

from datakeel.core.errors import ValidationError
from datakeel.versioning.inspect_v2 import (
    LEDGER,
    LEDGER_SQL,
    LEDGER_TRIGGERS,
    facts_digest,
    normalize_sql,
    quote,
    schema_objects,
)
from datakeel.versioning.models import (
    BaselineDefinition,
    DatabaseStatus,
    LedgerRecord,
    MigrationDefinition,
    SchemaObject,
)

__all__ = [
    "LEDGER",
    "LEDGER_SQL",
    "LEDGER_TRIGGERS",
    "facts_digest",
    "inspect_database",
    "normalize_sql",
    "schema_objects",
    "validate_baseline",
]


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


def _physical_forms(baseline: BaselineDefinition) -> tuple[BaselineDefinition, ...]:
    """Enumerate only the independently frozen physical forms of one baseline.

    SQLite ADD COLUMN regenerates the table DDL with the new column after the existing
    column list. v2 froze that real ALTER result for task_shards. v3 declares display_rank
    last in the typed model, so its ALTER form equals the typed export; only the inherited
    shard duality remains. No arbitrary reordered, extra or altered DDL is ever accepted.
    """
    if baseline.id not in {"sqlite-b2", "sqlite-b3"}:
        return (baseline,)
    alternate = TypeAdapter(SchemaObject).validate_json(
        files("datakeel.versioning").joinpath("sqlite_b2_altered_shards.json").read_bytes()
    )
    swapped = baseline.model_copy(
        update={
            "objects": tuple(
                alternate if item.name == alternate.name else item for item in baseline.objects
            )
        }
    )
    return (baseline, swapped)


def validate_baseline(connection: Connection, baseline: BaselineDefinition) -> None:
    """Match complete DDL and legal data independently of row count or fixture hashes."""
    expected = tuple(
        tuple(item.model_copy(update={"sql": normalize_sql(item.sql)}) for item in form.objects)
        for form in _physical_forms(baseline)
    )
    if schema_objects(connection) not in expected:
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
        for form in _physical_forms(definition.target):
            expected = tuple(
                item.model_copy(update={"sql": normalize_sql(item.sql)}) for item in form.objects
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
