# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomic latest-baseline stamps and compatibility with the independent toy registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from datakeel.core.settings import Settings
from datakeel.versioning.campaign_v2 import status, upgrade
from datakeel.versioning.inspect import facts_digest, schema_objects
from datakeel.versioning.registry import registry
from tests.versioning.helpers import seed_toy, toy_registry
from tests.versioning.test_baselines import legacy

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("fault", ["ledger", "facts"])
def test_latest_stamp_rolls_back_all_ledger_rows_without_business_ddl(
    unmigrated_db: Database, tmp_path: Path, fault: str
) -> None:
    """Failure after the actual second stamp never leaves a v1 ledger on a v2 schema."""
    path = legacy(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO datasets VALUES ('d','original',1,'[]','{}',NULL,'{}','{}')"
        )
    with unmigrated_db.engine.connect() as connection:
        objects, facts = schema_objects(connection), facts_digest(connection)

    def after(
        conn: object, _cur: object, sql: str, params: object, _ctx: object, _many: object
    ) -> None:
        if sql.startswith("INSERT INTO datakeel_schema_versions") and params[0] == 2:
            if fault == "ledger":
                msg = "stamp ledger fault"
                raise RuntimeError(msg)
            conn.exec_driver_sql("UPDATE datasets SET name='forged'")

    event.listen(Engine, "after_cursor_execute", after)
    try:
        result = upgrade(path, Settings(home=tmp_path), registry())
    finally:
        event.remove(Engine, "after_cursor_execute", after)
    assert result.exit_code == 5, "W4-v2-stamp-postcheck"
    assert result.version == 0
    with unmigrated_db.engine.connect() as connection:
        assert not schema_objects(connection, system=True), "W4-v2-stamp-all-ledger-atomic"
        assert schema_objects(connection) == objects
        assert facts_digest(connection) == facts
    assert upgrade(path, Settings(home=tmp_path), registry()).exit_code == 0
    assert len(list((tmp_path / "backups").iterdir())) == 1


@pytest.mark.parametrize("fault", ["", "ddl", "data"])
def test_v2_runner_retains_toy_registry_semantics(tmp_path: Path, fault: str) -> None:
    """Explicit fact-transforming toy versions still commit or roll back at the same boundary."""
    path = tmp_path / "toy.sqlite"
    seed_toy(path)
    result = upgrade(path, Settings(home=tmp_path / "home"), toy_registry(fault))
    assert result.exit_code == (5 if fault else 0)
    assert result.version == (1 if fault else 2)
    assert status(path, tmp_path / "home", toy_registry()).state == (
        "pending" if fault else "current"
    )


def test_latest_stamp_emits_only_system_ddl(unmigrated_db: Database, tmp_path: Path) -> None:
    """Recognition/stamping does not rewrite any business schema or issue data writes."""
    path = legacy(unmigrated_db)
    writes: list[str] = []

    def after(_c: object, _cur: object, sql: str, _p: object, _ctx: object, _many: object) -> None:
        if sql.lstrip().split()[0].upper() in {
            "CREATE",
            "ALTER",
            "DROP",
            "INSERT",
            "UPDATE",
            "DELETE",
        }:
            writes.append(sql)

    event.listen(Engine, "after_cursor_execute", after)
    try:
        result = upgrade(path, Settings(home=tmp_path), registry())
    finally:
        event.remove(Engine, "after_cursor_execute", after)
    assert result.exit_code == 0
    assert len(writes) == 5  # One ledger table, two ledger triggers, two ledger rows.
    assert all("datakeel_schema_versions" in sql for sql in writes), "W4-v2-no-business-ddl"
