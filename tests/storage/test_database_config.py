# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Database URL selection across normal and read-only connections."""

from pathlib import Path

import pytest
from sqlalchemy import text

from datakeel.persistence import migrate
from datakeel.storage.database import Database


def test_configured_database_url_is_used_for_normal_and_read_only_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit settings URL must not fall back to the home database."""
    database = tmp_path / "configured.db"
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", f"sqlite:///{database}")
    migrate(Database())
    for read_only in (False, True):
        db = Database(read_only=read_only)
        assert db.engine.url.database
        assert db.engine.url.database.endswith(str(database))
        with db.session() as session:
            assert session.execute(text("SELECT 1")).scalar_one() == 1
        db.engine.dispose()
