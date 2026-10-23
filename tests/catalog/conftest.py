# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synthetic local database sources for metadata reflection and lineage tests."""

import sqlite3
from pathlib import Path

import pytest

from datakeel.core.catalog_models import CatalogImportRequest


@pytest.fixture
def source_request(tmp_path: Path) -> CatalogImportRequest:
    """Create a self-contained source with keys, joins, arithmetic, and a CTE view."""
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE regions(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE sales(id INTEGER PRIMARY KEY, region_id INTEGER REFERENCES regions(id),
                               amount REAL NOT NULL, day DATE);
            CREATE VIEW sales_view AS SELECT s.id, s.amount * 2 AS doubled, r.name
                FROM sales s JOIN regions r ON r.id = s.region_id;
            CREATE VIEW daily AS WITH totals AS (
                SELECT day, SUM(amount) AS total FROM sales GROUP BY day)
                SELECT day, total FROM totals;
        """)
    return CatalogImportRequest(
        source_id="sample", name="Synthetic source", connection_url=f"sqlite:///{path}"
    )
