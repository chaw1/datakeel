# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small registered metric fixtures independent of enterprise demo generation."""

import sqlite3
from pathlib import Path

import pytest

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.metric_models import (
    DimensionDefinition,
    Measure,
    MetricDefinition,
    MetricTime,
    SemanticLayer,
    TermDefinition,
    TermTarget,
)
from datakeel.core.models import AssetRef


@pytest.fixture
def layer() -> SemanticLayer:
    """Describe a region-sliced and date-filtered revenue metric."""
    return SemanticLayer(
        metrics=[
            MetricDefinition(
                id="revenue",
                name="零售额",
                synonyms=["零售收入"],
                description="Completed revenue",
                owner="Retail team",
                measure=Measure(
                    table="test/main/orders",
                    column="test/main/orders/amount",
                    aggregation="sum",
                ),
                time=MetricTime(column="test/main/orders/date"),
                dimensions=["region"],
                caveats=["Synthetic"],
            )
        ],
        dimensions=[
            DimensionDefinition(
                id="region", name="区域", column="test/main/orders/region", values=["华东", "华北"]
            )
        ],
        terms=[TermDefinition(term="零售额", means=TermTarget(kind="metric", id="revenue"))],
    )


@pytest.fixture
def catalog() -> CatalogSnapshot:
    """Register every field required by the test metric."""
    identities = [("table", "test/main/orders")]
    identities.extend(
        ("column", f"test/main/orders/{name}") for name in ("amount", "region", "date")
    )
    return CatalogSnapshot(
        scope="test",
        objects=tuple(
            CatalogObject(
                asset_ref=AssetRef(asset_type=kind, asset_id=identity),
                name=identity.rsplit("/", 1)[-1],
            )
            for kind, identity in identities
        ),
    )


@pytest.fixture
def source_url(tmp_path: Path) -> str:
    """Create a tiny independent query source with an injection-looking dimension value."""
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE orders(amount REAL, region TEXT, date TEXT)")
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?, ?)",
            [
                (10.0, "华东", "2026-07-01"),
                (20.0, "华东", "2026-09-30"),
                (40.0, "华北", "2026-08-05"),
                (80.0, "华东", "2026-10-01"),
                (160.0, "华东' OR 1=1 --", "2026-08-01"),
            ],
        )
    return f"sqlite:///{path}"
