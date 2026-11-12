# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The claim-order index converges to the persisted display rank on PostgreSQL startup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.storage.production_team_rows import install_team_constraints

if TYPE_CHECKING:
    from datakeel.storage.database import Database

_LOOKUP = "SELECT indexdef FROM pg_indexes WHERE indexname = 'production_task_claim_order'"


def test_claim_index_converges_from_the_pre_rank_definition(db: Database) -> None:
    """A store migrated before persisted ranks rebuilds the index once, then keeps it."""
    if db.sqlite:
        pytest.skip("SQLite converges through schema v3; the installer only sees empty stores")
    with db.engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX production_task_claim_order")
        connection.exec_driver_sql(
            "CREATE INDEX production_task_claim_order "
            "ON production_tasks (project_id, state, priority DESC, id)"
        )
        install_team_constraints(connection, sqlite=False)
        definition = connection.exec_driver_sql(_LOOKUP).scalar_one()
        assert "display_rank" in definition
        install_team_constraints(connection, sqlite=False)
        assert connection.exec_driver_sql(_LOOKUP).scalar_one() == definition
