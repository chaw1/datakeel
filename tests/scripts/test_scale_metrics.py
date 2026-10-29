# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Metric workloads check generated facts independently through the full ask boundary."""

from pathlib import Path

from sqlalchemy import text

from datakeel.ask.service import ask_data
from datakeel.storage.database import Database
from scripts.scale_bench.metrics import prepare, request, run, valid_answer
from scripts.scale_bench.models import SCALES, Config, Context


def _context(db: Database, root: Path, seed: int = 23) -> Context:
    schema = None
    if not db.sqlite:
        with db.engine.connect() as connection:
            schema = str(connection.execute(text("SELECT current_schema()")).scalar_one())
    return Context(
        config=Config(scenario="B4", seed=seed, repeats=2),
        scale=SCALES["S"],
        db=db,
        root=root,
        schema_name=schema,
    )


def test_metric_fixture_answers_match_independent_oracle(db: Database, tmp_path: Path) -> None:
    """Full and sliced questions must return exact generator-derived integer sums."""
    context = _context(db, tmp_path, seed=-23)
    fixture = prepare(context)
    for index in (0, 1):
        assert valid_answer(ask_data(db, request(index)), fixture, index)
    expected = sum((index * 1664525 - 23) % 10000 for index in range(1000))
    assert fixture.expected_total == expected


def test_metric_workload_measures_twenty_concurrent_answers(db: Database, tmp_path: Path) -> None:
    """Serial and concurrent measurements include persisted evidence with zero oracle errors."""
    result = run(_context(db, tmp_path))
    assert result.latencies["serial_ask"].count == 2
    assert result.latencies["concurrent_ask"].count == 20
    assert result.latencies["concurrent_ask"].errors == 0
    assert result.latencies["serial_ask"].errors == 0
