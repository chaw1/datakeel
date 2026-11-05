# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application construction admits current stores and never implicitly upgrades."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text

from datakeel.api.app import create_app
from datakeel.core.errors import ValidationError
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from datakeel.core.schema import CanonicalSchema, SchemaContribution


@pytest.mark.parametrize("enabled", [False, True])
def test_create_app_rejects_empty_database_even_with_legacy_flag(
    unmigrated_db: Database, *, enabled: bool
) -> None:
    """The retained keyword is call compatibility, never a migration authorization."""
    with pytest.raises(ValidationError, match=r"Database (missing|empty)"):
        create_app(unmigrated_db, run_migrations=enabled)
    assert inspect(unmigrated_db.engine).get_table_names() == []


def test_create_app_reuses_current_database_without_migration(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current startup performs admission before recovery without any schema initializer."""

    def fail(
        database: Database,
        contributions: tuple[SchemaContribution, ...],
        *,
        canonical: CanonicalSchema,
    ) -> None:
        pytest.fail("Startup must not call schema initialization")

    monkeypatch.setattr(Database, "migrate", fail)
    assert create_app(db, run_migrations=False).state.db is db


@pytest.mark.parametrize("enabled", [False, True])
def test_create_app_rejects_unknown_table_without_optout(db: Database, *, enabled: bool) -> None:
    """The legacy keyword cannot bypass conservative full schema recognition."""
    with db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE scale_facts (value INTEGER)"))
    with pytest.raises(ValidationError, match="Database invalid"):
        create_app(db, run_migrations=enabled)
