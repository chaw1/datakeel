# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The claim-order index converges to the persisted display rank on PostgreSQL startup."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from datakeel.storage.production_team_rows import install_team_constraints

if TYPE_CHECKING:
    from datakeel.storage.database import Database

_LOOKUP = (
    "SELECT indexdef FROM pg_indexes WHERE indexname = 'production_task_claim_order' "
    "AND tablename = 'production_tasks' AND schemaname = current_schema()"
)


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


def test_claim_index_upgrade_ignores_a_shadow_index_on_another_table(db: Database) -> None:
    """Resolve the index by its table even if another schema shadows the index name."""
    if db.sqlite:
        pytest.skip("PostgreSQL resolves index names through a search path")
    with db.engine.connect() as connection:
        original_path = connection.exec_driver_sql("SHOW search_path").scalar_one()
        connection.exec_driver_sql("DROP INDEX production_task_claim_order")
        connection.exec_driver_sql(
            "CREATE INDEX production_task_claim_order "
            "ON production_tasks (project_id, state, priority DESC, id)"
        )
        connection.exec_driver_sql("CREATE SCHEMA claim_index_shadow")
        connection.exec_driver_sql("CREATE TABLE claim_index_shadow.unrelated (id text)")
        connection.exec_driver_sql(
            "CREATE INDEX production_task_claim_order ON claim_index_shadow.unrelated (id)"
        )
        connection.execute(
            text("SELECT set_config('search_path', :path, true)"),
            {"path": f"claim_index_shadow, {original_path}"},
        )
        shadow_query = "SELECT pg_get_indexdef('production_task_claim_order'::regclass)"
        shadow_definition = connection.exec_driver_sql(shadow_query).scalar_one()
        install_team_constraints(connection, sqlite=False)
        assert connection.exec_driver_sql(shadow_query).scalar_one() == shadow_definition
        connection.execute(
            text("SELECT set_config('search_path', :path, true)"), {"path": original_path}
        )
        assert "display_rank" in connection.exec_driver_sql(_LOOKUP).scalar_one()
