# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independently exercise production constraints in the complete frozen latest target."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.storage.database import Database
from datakeel.versioning.v3 import baseline
from tests.storage.test_production_workflow import (
    test_database_enforces_one_active_assignment_per_task_stage as assignment_constraint,
)
from tests.storage.test_production_workflow import (
    test_revision_database_rejects_update_and_delete as revision_constraint,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def frozen_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    """Use real SQLite and all frozen DDL, independent of a mutable typed initializer."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    database = Database(f"sqlite:///{tmp_path / 'target.sqlite'}")
    with database.engine.begin() as connection:
        for kind in ("table", "index", "trigger", "view"):
            for item in baseline().objects:
                if item.kind == kind:
                    connection.exec_driver_sql(item.sql)
    try:
        yield database
    finally:
        database.engine.dispose()


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_revision_database_rejects_update_and_delete(
    frozen_target: Database, operation: str
) -> None:
    """Direct revision writes obey the complete frozen target's immutable-history trigger."""
    revision_constraint(frozen_target, operation)


def test_database_enforces_one_active_assignment_per_task_stage(frozen_target: Database) -> None:
    """Direct duplicate assignment obeys the frozen target's unique partial index."""
    assignment_constraint(frozen_target)
