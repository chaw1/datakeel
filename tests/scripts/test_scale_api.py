# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP workload statistics retain bounded memory and actual route behavior."""

from pathlib import Path

from sqlalchemy import text

from datakeel.storage.database import Database
from scripts.scale_bench.api import Histogram, run
from scripts.scale_bench.models import SCALES, Config, Context


def test_histogram_nearest_rank_quantiles_and_errors_are_bounded() -> None:
    """A long request stream changes counters without retaining individual samples."""
    histogram = Histogram()
    allocated = len(histogram.buckets)
    for index in range(10000):
        histogram.add(index % 100 + 0.1, error=index % 2 == 0)
    result = histogram.summary()
    assert len(histogram.buckets) == allocated
    assert result.count == 10000
    assert result.errors == 5000
    assert (result.p50_ms, result.p95_ms, result.p99_ms) == (50, 95, 99)


def test_histogram_empty_and_overflow_remain_explicit() -> None:
    """No samples return zeros; overflow retains the actual worst duration."""
    histogram = Histogram()
    assert histogram.summary().count == 0
    histogram.add(61_000)
    assert histogram.overflow == 1
    assert histogram.summary().max_ms == 61_000


def test_api_workload_exercises_all_four_http_routes(db: Database, tmp_path: Path) -> None:
    """A small real-ASGI run must validate every response and answer oracle."""
    schema = None
    if not db.sqlite:
        with db.engine.connect() as connection:
            schema = str(connection.execute(text("SELECT current_schema()")).scalar_one())
    context = Context(
        config=Config(scenario="B5"),
        db=db,
        root=tmp_path,
        schema_name=schema,
        scale=SCALES["S"].model_copy(update={"duration_seconds": 1}),
    )
    result = run(context)
    assert result.metrics["error_rate"] == 0
    assert set(result.latencies) == {"list", "search", "object", "ask", "all"}
    assert all(item.count > 0 for item in result.latencies.values())


def test_api_workload_measures_every_route_when_deadline_passes_first(
    db: Database, tmp_path: Path
) -> None:
    """A runner too slow to start users before the deadline still measures each route once."""
    schema = None
    if not db.sqlite:
        with db.engine.connect() as connection:
            schema = str(connection.execute(text("SELECT current_schema()")).scalar_one())
    context = Context(
        config=Config(scenario="B5"),
        db=db,
        root=tmp_path,
        schema_name=schema,
        scale=SCALES["S"].model_copy(update={"duration_seconds": 1e-9}),
    )
    result = run(context)
    assert result.metrics["error_rate"] == 0
    assert {key: item.count for key, item in result.latencies.items()} == {
        "list": 1,
        "search": 1,
        "object": 1,
        "ask": 1,
        "all": 4,
    }
