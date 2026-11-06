# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise SQLite-only campaigns independently of the application's selected test stack."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def unmigrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Database]:
    """Keep full-baseline and recovery fixtures local SQLite even in PostgreSQL CI jobs."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    try:
        yield database
    finally:
        database.engine.dispose()
