# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject incomplete schema wiring before writes and verify the actual canonical tables."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as ModelValidationError
from sqlalchemy import inspect, text

from datakeel.core.errors import ValidationError
from datakeel.core.schema import CanonicalSchema, SchemaContribution, validate_contributions
from datakeel.persistence import migrate
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Connection

    from datakeel.storage.database import Database


def test_empty_database_when_migrated_has_exactly_99_owned_tables(unmigrated_db: Database) -> None:
    """Empty initialization and repeated migration both satisfy the independent oracle."""
    assert inspect(unmigrated_db.engine).get_table_names() == []
    migrate(unmigrated_db)
    migrate(unmigrated_db)
    actual = set(inspect(unmigrated_db.engine).get_table_names())
    system = {"datakeel_schema_versions"} if unmigrated_db.sqlite else set()
    assert actual - system == {item.table for item in canonical_schema().tables}
    assert len(actual - system) == 99


def _broken(kind: str) -> tuple[SchemaContribution, ...]:
    items = list(schema_contributions())
    dataset = next(i for i, item in enumerate(items) if item.owner == "dataset_store")
    item = items[dataset]
    if kind == "missing-owner":
        items.pop()
    elif kind == "duplicate-owner":
        items.append(items[0])
    elif kind == "owner-order":
        items.reverse()
    elif kind == "duplicate-order":
        items[1] = items[1].model_copy(update={"order": 0})
    elif kind == "missing-row":
        items[dataset] = item.model_copy(update={"rows": item.rows[1:]})
    elif kind == "duplicate-row":
        items[dataset] = item.model_copy(update={"rows": (*item.rows, item.rows[0])})
    elif kind == "wrong-owner":
        items[0] = items[0].model_copy(update={"rows": (*items[0].rows, item.rows[0])})
        items[dataset] = item.model_copy(update={"rows": item.rows[1:]})
    elif kind == "missing-installer":
        items[dataset] = item.model_copy(update={"installers": item.installers[1:]})
    elif kind == "duplicate-installer":
        items[dataset] = item.model_copy(
            update={"installers": (*item.installers, item.installers[0])}
        )
    else:
        items[dataset] = item.model_copy(update={"installers": tuple(reversed(item.installers))})
    return tuple(items)


@pytest.mark.parametrize(
    "kind",
    [
        "missing-owner",
        "duplicate-owner",
        "owner-order",
        "duplicate-order",
        "missing-row",
        "duplicate-row",
        "wrong-owner",
        "missing-installer",
        "duplicate-installer",
        "installer-order",
    ],
)
def test_invalid_proposed_schema_fails_before_empty_initialization(
    unmigrated_db: Database, kind: str
) -> None:
    """Loaded global metadata cannot rescue any incomplete or ambiguous contribution."""
    with pytest.raises(ValidationError):
        unmigrated_db.migrate(_broken(kind), canonical=canonical_schema())
    assert inspect(unmigrated_db.engine).get_table_names() == []


def test_simultaneously_omitted_import_and_contribution_is_rejected() -> None:
    """A fresh interpreter with only three rows cannot infer a smaller valid oracle."""
    source = Path(__file__).resolve().parents[2]
    code = """
import json
from pathlib import Path
from datakeel.core.schema import Base, CanonicalSchema, TableOwner, validate_contributions
from datakeel.core.errors import ValidationError
from datakeel.worker_store.schema import SCHEMA
entries = json.loads(Path('datakeel/persistence/canonical_tables.json').read_text())
canonical = CanonicalSchema(tables=tuple(TableOwner(table=e['table'], owner=e['owner'])
    for e in entries), owners=tuple(sorted({e['owner'] for e in entries})), installers=())
assert len(Base.metadata.tables) == 3
try:
    validate_contributions((SCHEMA,), canonical)
except ValidationError:
    pass
else:
    raise AssertionError('Missing imports and contributions accepted')
"""
    result = subprocess.run(  # noqa: S603  # Fixed isolated local interpreter, no services.
        [sys.executable, "-c", code],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_actual_database_with_unexpected_table_is_rejected(unmigrated_db: Database) -> None:
    """Postflight compares the live set rather than trusting the proposed set."""
    with unmigrated_db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE unexpected_table (id INTEGER PRIMARY KEY)"))
    with pytest.raises(
        ValidationError, match=r"Database invalid|empty database|Canonical tables mismatch"
    ):
        migrate(unmigrated_db)
    assert inspect(unmigrated_db.engine).get_table_names() == ["unexpected_table"]


def test_contributions_and_installers_are_frozen_and_forbid_extras() -> None:
    """The wiring boundary rejects mutation and unknown configuration."""
    contribution = schema_contributions()[0]
    with pytest.raises(ModelValidationError):
        contribution.owner = "changed"  # type: ignore[misc]
    with pytest.raises(ModelValidationError):
        SchemaContribution.model_validate({**contribution.model_dump(), "unknown": True})


def test_installer_execution_retains_historical_order(unmigrated_db: Database) -> None:
    """Explicit owner grouping cannot change the historical installer sequence."""
    seen: list[str] = []

    def track(key: str, original: Callable[..., None]) -> Callable[..., None]:
        def install(connection: Connection, *, sqlite: bool) -> None:
            seen.append(key)
            original(connection, sqlite=sqlite)

        return install

    contributions = tuple(
        item.model_copy(
            update={
                "installers": tuple(
                    installer.model_copy(
                        update={"install": track(installer.key, installer.install)}
                    )
                    for installer in item.installers
                )
            }
        )
        for item in schema_contributions()
    )
    unmigrated_db.migrate(contributions, canonical=canonical_schema())
    assert seen == [
        "file_discovery",
        "evidence",
        "release",
        "asset",
        "training",
        "llm_data",
        "production",
        "lineage",
    ]


def test_empty_canonical_cannot_hide_registered_tables() -> None:
    """Even an empty proposed and canonical pair cannot silently create registered rows."""
    with pytest.raises(ValidationError, match="Canonical tables mismatch"):
        validate_contributions((), CanonicalSchema(tables=(), owners=(), installers=()))


def test_lineage_pg_installer_emits_the_original_sql_without_connecting() -> None:
    """Exercise offline SQL emission only; this does not claim a PostgreSQL migration test."""
    from unittest.mock import create_autospec  # noqa: PLC0415  # Only this test needs the mock.

    from sqlalchemy.engine import Connection  # noqa: PLC0415  # Autospec needs the runtime class.

    from datakeel.dataset_store.schema import install_lineage  # noqa: PLC0415  # Isolated installer.

    connection = create_autospec(Connection, instance=True)
    install_lineage(connection, sqlite=False)
    emitted = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert len(emitted) == 2
    assert "CREATE OR REPLACE FUNCTION datakeel_immutable_event()" in emitted[0]
    assert "AND tgrelid = 'lineage_events'::regclass" in emitted[1]
    assert "BEFORE UPDATE OR DELETE ON lineage_events" in emitted[1]
