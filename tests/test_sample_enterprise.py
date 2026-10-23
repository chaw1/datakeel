# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify reproducible fictional sources, relational validity, and independent gold."""

import hashlib
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import pytest

from datakeel.sample_enterprise import EnterpriseGold, EnterpriseSample, generate_enterprise
from datakeel.sample_enterprise.crm import build_crm
from datakeel.sample_enterprise.ecommerce import build_ecommerce
from datakeel.sample_enterprise.erp import build_erp
from datakeel.sample_enterprise.models import SourceData
from datakeel.sample_enterprise.service import build_service
from examples.enterprise.generate import main


@pytest.fixture(scope="module")
def enterprise_sample(tmp_path_factory: pytest.TempPathFactory) -> EnterpriseSample:
    """Materialize the canonical enterprise data once for read-only checks."""
    return generate_enterprise(tmp_path_factory.mktemp("enterprise"))


def _hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir()
        if path.is_file()
    }


def _dump_hashes(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in directory.glob("*.sqlite"):
        with closing(sqlite3.connect(path)) as database:
            exported = "\n".join(database.iterdump()).encode("utf-8")
        result[path.name] = hashlib.sha256(exported).hexdigest()
    return result


def test_generator_repeated_output_byte_identical(tmp_path: Path) -> None:
    """Repeated generation preserves every database byte and independent gold byte."""
    started = perf_counter()
    first = generate_enterprise(tmp_path)
    original = _hashes(tmp_path)
    original_dumps = _dump_hashes(tmp_path)
    repeated = generate_enterprise(tmp_path)
    assert (repeated, _hashes(tmp_path)) == (first, original)
    assert _dump_hashes(tmp_path) == original_dumps
    assert perf_counter() - started < 30


def test_generator_expected_size_counts_and_reference(enterprise_sample: EnterpriseSample) -> None:
    """Keep the fixture at about fifty thousand rows with four multi-table sources."""
    assert (
        len(enterprise_sample.sources),
        enterprise_sample.row_count,
        sum(source.table_count for source in enterprise_sample.sources),
        sum(source.view_count for source in enterprise_sample.sources),
        enterprise_sample.reference_instant,
    ) == (4, 51992, 20, 4, datetime(2026, 10, 1, tzinfo=UTC))


@pytest.mark.parametrize("builder", [build_erp, build_crm, build_ecommerce, build_service])
def test_source_builders_generate_self_contained_data(builder: Callable[[], SourceData]) -> None:
    """Every packaged source exposes five typed tables and a lineage-bearing view."""
    source = builder()
    assert len(source.tables) == 5
    assert all(len(row) == len(table.columns) for table in source.tables for row in table.rows)
    assert len(source.views) == 1


def test_generator_relational_integrity_and_views(enterprise_sample: EnterpriseSample) -> None:
    """Validate primary/foreign keys and execute each reflected view."""
    for source in enterprise_sample.sources:
        with closing(sqlite3.connect(source.path)) as database:
            assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert database.execute("PRAGMA foreign_key_check").fetchall() == []
            views = database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            ).fetchall()
            for (name,) in views:
                # Names originate from the generated SQLite schema, not user input.
                cursor = database.execute(f'SELECT * FROM "{name}" LIMIT 1')  # noqa: S608
                assert len(cursor.description) >= 5
                assert cursor.fetchone() is not None


def test_gold_numeric_answers_are_fixed_independent_values(
    enterprise_sample: EnterpriseSample,
) -> None:
    """Pin Python-computed results so data or gold-rule changes are explicit."""
    gold = EnterpriseGold.model_validate_json(enterprise_sample.gold_path.read_text())
    assert gold.answers == {
        "ok-east-retail-last-quarter": 4979475.0,
        "ok-retail-march-synonym": 6875982.0,
        "ok-east-shipments-last-quarter": 5589975.0,
        "ok-east-sales-last-quarter": 3290330.0,
        "ok-orders-march": 1860.0,
        "ok-refunds-march": 38305.0,
        "ok-east-inventory": 4600.0,
        "ok-east-customers": 300.0,
        "ok-east-tickets-last-quarter": 105.0,
        "ok-repairs-march": 12203.0,
        "ok-online-payments-march": 117932.0,
        "ok-south-sales-units-last-quarter": 1846.0,
        "ok-tickets-last-30-days": 132.0,
        "ok-online-retail-last-quarter": 3310428.0,
    }


def test_gold_quarter_answer_matches_direct_sql(enterprise_sample: EnterpriseSample) -> None:
    """Cross-check the flagship benchmark using a separate handwritten SQL query."""
    source = next(source for source in enterprise_sample.sources if source.id == "ecommerce")
    with closing(sqlite3.connect(source.path)) as database:
        result = database.execute(
            "SELECT sum(paid_amount) FROM orders WHERE status = ? AND region = ? "
            "AND date >= ? AND date < ?",
            ("completed", "华东", "2026-07-01", "2026-10-01"),
        ).fetchone()
    gold = EnterpriseGold.model_validate_json(enterprise_sample.gold_path.read_text())
    assert result == (gold.answers["ok-east-retail-last-quarter"],)


def test_cli_wrapper_generates_requested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The required example command calls the packaged generator and reports counts."""
    monkeypatch.setattr("sys.argv", ["generate", "--output", str(tmp_path)])
    main()
    assert "51992 rows" in capsys.readouterr().out
    assert (tmp_path / "gold.json").is_file()
