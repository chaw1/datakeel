# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent synthetic multi-version fixture, never a claimed historical release."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from datakeel.core.settings import Settings
from datakeel.versioning.campaign import upgrade
from datakeel.versioning.models import BaselineDefinition, MigrationDefinition, SchemaObject

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.engine import Connection

ITEMS = "CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT NOT NULL)"
AUDIT = "CREATE TABLE audit (seq INTEGER PRIMARY KEY, value TEXT NOT NULL)"
CHANGED = (
    "CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT NOT NULL, "
    "note TEXT NOT NULL DEFAULT '')"
)


def toy_registry(fault: str = "") -> tuple[MigrationDefinition, ...]:
    """Freeze schema and invariant expectations independently of the forward handler."""
    initial = BaselineDefinition(
        id="toy-b1",
        releases=("synthetic-a", "synthetic-b"),
        objects=(
            SchemaObject(kind="table", name="audit", table="audit", sql=AUDIT),
            SchemaObject(kind="table", name="items", table="items", sql=ITEMS),
        ),
    )
    target = initial.model_copy(
        update={
            "id": "toy-b2",
            "objects": (initial.objects[0], initial.objects[1].model_copy(update={"sql": CHANGED})),
            "invariants": (
                "SELECT 1 FROM items WHERE note != 'converted' OR label != upper(label)",
            ),
        }
    )

    def first(_connection: Connection) -> None:
        pass

    def second(connection: Connection) -> None:
        connection.exec_driver_sql("ALTER TABLE items ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        fail("ddl", connection)
        connection.exec_driver_sql("UPDATE items SET label=upper(label), note='converted'")
        connection.exec_driver_sql("INSERT INTO audit VALUES (2, 'converted')")
        fail("data", connection)

    def fail(stage: str, connection: Connection) -> None:
        _assert_fault_facts(connection, stage)
        if fault == stage:
            raise RuntimeError(stage)
        if fault == "die-" + stage:
            os._exit(73)  # Deliberate hard process death, exercising OS lock/DB rollback.

    return (
        MigrationDefinition(
            version=1, checksum="1" * 64, source="toy-b1", target=initial, forward=first
        ),
        MigrationDefinition(
            version=2,
            checksum="2" * 64,
            source="toy-b1",
            target=target,
            forward=second,
            preserve_facts=False,
        ),
    )


def seed_toy(path: Path) -> None:
    """Write fixed full-field facts with an explicit audit order."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql(ITEMS)
        connection.exec_driver_sql(AUDIT)
        connection.exec_driver_sql("INSERT INTO items VALUES (1, 'one'), (2, 'two')")
        connection.exec_driver_sql("INSERT INTO audit VALUES (1, 'original')")
    engine.dispose()


def ledger_fault(fault: str) -> None:
    """Inject only after SQLite has actually inserted the second ledger record."""

    def after(
        _conn: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _many: object,
    ) -> None:
        if statement.startswith("INSERT INTO datakeel_schema_versions"):
            assert isinstance(parameters, tuple)
            if parameters[0] == 2:
                from sqlalchemy.engine import Connection  # noqa: PLC0415

                assert isinstance(_conn, Connection)
                assert _conn.exec_driver_sql(
                    "SELECT version FROM datakeel_schema_versions ORDER BY version"
                ).fetchall() == [(1,), (2,)], "W4-fault-after-real-ledger"
                assert _conn.exec_driver_sql("SELECT * FROM items ORDER BY id").fetchall() == [
                    (1, "ONE", "converted"),
                    (2, "TWO", "converted"),
                ], "W4-ledger-after-full-data"
                if fault == "die-ledger":
                    os._exit(73)
                if fault == "ledger":
                    msg = "ledger"
                    raise RuntimeError(msg)

    event.listen(Engine, "after_cursor_execute", after)


def run_toy(path: Path, home: Path, fault: str = "") -> int:
    """Run an actual campaign from a subprocess without starting application services."""
    if fault.endswith("ledger"):
        ledger_fault(fault)
    report = upgrade(path, Settings(home=home), toy_registry(fault))
    sys.stdout.write(report.model_dump_json() + "\n")
    return report.exit_code


def _assert_fault_facts(connection: Connection, stage: str) -> None:
    rows = connection.exec_driver_sql("SELECT * FROM items ORDER BY id").fetchall()
    if stage == "ddl":
        assert rows == [(1, "one", ""), (2, "two", "")], "W4-fault-after-real-ddl"
        assert connection.exec_driver_sql("SELECT * FROM audit").fetchall() == [(1, "original")]
    else:
        assert rows == [(1, "ONE", "converted"), (2, "TWO", "converted")], (
            "W4-fault-after-real-data"
        )
        assert connection.exec_driver_sql("SELECT * FROM audit ORDER BY seq").fetchall() == [
            (1, "original"),
            (2, "converted"),
        ], "W4-fault-data-audit"
