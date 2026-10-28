# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every rule type passes on the generated enterprise sample and fails on injected defects."""

import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqParameters, DqResult, DqRule, DqTarget
from datakeel.quality.dq_engine import execute_rule
from datakeel.sample_enterprise import EnterpriseSample, generate_enterprise

# The sample documents 2026-10-01T00:00:00Z as its reference instant.
REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)
LARGE_TABLE_SCAN = 20000


@pytest.fixture(scope="module")
def pristine(tmp_path_factory: pytest.TempPathFactory) -> EnterpriseSample:
    """Generate the fictional enterprise sources once; each case works on its own copy."""
    return generate_enterprise(tmp_path_factory.mktemp("enterprise"))


def source_copy(sample: EnterpriseSample, source_id: str, folder: Path) -> SourceProperties:
    """Copy one generated SQLite source so injected defects never leak between cases."""
    original = next(item.path for item in sample.sources if item.id == source_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / original.name
    shutil.copyfile(original, target)
    return SourceProperties(connection_url=f"sqlite:///{target}", dialect="sqlite")


def inject(source: SourceProperties, *statements: str) -> None:
    """Corrupt the copied business source with ordinary SQL writes."""
    path = (source.connection_url or "").removeprefix("sqlite:///")
    with sqlite3.connect(path) as connection:
        for statement in statements:
            connection.execute(statement)


def rule(source_id: str, table: str, column: str | None, kind: str, **settings: object) -> DqRule:
    """Build a rule against a real generated table, with optional scan budget and threshold."""
    return DqRule.model_validate(
        {
            "id": f"{table}-{kind}",
            "name": f"{table} {kind}",
            "owner": "quality-team",
            "target": DqTarget(source_id=source_id, table=table, column=column),
            "kind": kind,
            **settings,
        }
    )


ROW_CASES = (
    pytest.param(
        rule("ecommerce", "orders", "region", "not_null", max_rows=LARGE_TABLE_SCAN),
        ("UPDATE orders SET region = NULL WHERE id IN (7, 4242, 17999)",),
        3,
        id="not_null",
    ),
    pytest.param(
        rule("crm", "customers", "name", "unique"),
        (
            "UPDATE customers SET name = (SELECT name FROM customers WHERE id = 5) WHERE id = 600",
            "UPDATE customers SET name = (SELECT name FROM customers WHERE id = 5) WHERE id = 1100",
        ),
        3,
        id="unique",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "orders",
            "paid_amount",
            "range",
            params=DqParameters(minimum=1, maximum=10000),
            max_rows=LARGE_TABLE_SCAN,
        ),
        (
            "UPDATE orders SET paid_amount = -50 WHERE id = 11",
            "UPDATE orders SET paid_amount = 250000 WHERE id = 12",
        ),
        2,
        id="range",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "orders",
            "status",
            "accepted_values",
            params=DqParameters(values=("completed", "cancelled")),
            max_rows=LARGE_TABLE_SCAN,
        ),
        ("UPDATE orders SET status = 'COMPLETED' WHERE id IN (20, 21)",),
        2,
        id="accepted_values",
    ),
    pytest.param(
        rule(
            "crm",
            "sales",
            "region",
            "accepted_values",
            params=DqParameters(reference_table="regions", reference_column="name"),
        ),
        ("UPDATE sales SET region = '未登记区域' WHERE id IN (30, 31)",),
        2,
        id="accepted_values_code_table",
    ),
    pytest.param(
        rule("crm", "customers", "name", "regex", params=DqParameters(pattern=r"样例客户\d{4}")),
        (
            "UPDATE customers SET name = 'Customer 12' WHERE id = 12",
            "UPDATE customers SET name = '样例客户12' WHERE id = 13",
        ),
        2,
        id="regex",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "returns",
            "order_id",
            "referential_integrity",
            params=DqParameters(reference_table="orders", reference_column="id"),
            max_rows=LARGE_TABLE_SCAN,
        ),
        ("UPDATE returns SET order_id = 999999 WHERE id = 3",),
        1,
        id="referential_integrity",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "orders",
            None,
            "sql_assertion",
            params=DqParameters(
                sql="SELECT id FROM orders WHERE paid_amount > list_amount AND status = :status",
                bindings={"status": "completed"},
            ),
            max_rows=LARGE_TABLE_SCAN,
        ),
        ("UPDATE orders SET paid_amount = list_amount + 1 WHERE id IN (40, 41)",),
        2,
        id="sql_assertion",
    ),
)


@pytest.mark.parametrize(("definition", "defects", "expected"), ROW_CASES)
def test_row_rules_pass_clean_sample_and_count_injected_defects(
    pristine: EnterpriseSample,
    tmp_path: Path,
    definition: DqRule,
    defects: tuple[str, ...],
    expected: int,
) -> None:
    """Clean generated rows pass; only the deliberately corrupted rows are counted."""
    clean = source_copy(pristine, definition.target.source_id, tmp_path / "clean")
    passed = execute_rule(definition, clean, now=REFERENCE)
    assert (passed.status, passed.failed_count) == ("passed", 0)
    corrupted = source_copy(pristine, definition.target.source_id, tmp_path / "corrupted")
    inject(corrupted, *defects)
    failed = execute_rule(definition, corrupted, now=REFERENCE)
    assert (failed.status, failed.failed_count) == ("failed", expected)
    assert all(sample.value == "[REDACTED]" for sample in failed.samples)


def test_freshness_measures_latest_sample_timestamp_and_detects_stale_table(
    pristine: EnterpriseSample, tmp_path: Path
) -> None:
    """The newest order date is one day old; removing September makes it 31 days old."""
    definition = rule(
        "ecommerce", "orders", "date", "freshness", threshold=2 * 86400, max_rows=LARGE_TABLE_SCAN
    )
    clean = execute_rule(
        definition, source_copy(pristine, "ecommerce", tmp_path / "a"), now=REFERENCE
    )
    assert (clean.status, clean.actual_value) == ("passed", 86400)
    stale = source_copy(pristine, "ecommerce", tmp_path / "b")
    inject(stale, "DELETE FROM orders WHERE date >= '2026-09-01'")
    result = execute_rule(definition, stale, now=REFERENCE)
    assert (result.status, result.actual_value) == ("failed", 31 * 86400)


def baseline(definition: DqRule, source: SourceProperties) -> tuple[DqResult, ...]:
    """Collect three daily cold-start observations from the untouched sample."""
    history: tuple[DqResult, ...] = ()
    for days in (3, 2, 1):
        result = execute_rule(definition, source, history, REFERENCE - timedelta(days=days))
        assert result.status == "baseline_insufficient"
        history = (result, *history)
    return history


HISTORICAL_CASES = (
    pytest.param(
        rule("ecommerce", "payments", None, "volume_change", threshold=0.3),
        ("DELETE FROM payments WHERE id % 2 = 0",),
        id="volume_change",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "orders",
            "paid_amount",
            "distribution_drift",
            threshold=0.2,
            max_rows=LARGE_TABLE_SCAN,
        ),
        ("UPDATE orders SET paid_amount = paid_amount * 2 WHERE id % 2 = 0",),
        id="drift_mean",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "payments",
            "amount",
            "distribution_drift",
            params=DqParameters(statistic="stddev"),
            threshold=0.5,
        ),
        ("UPDATE payments SET amount = amount * 10 WHERE id % 10 = 0",),
        id="drift_stddev",
    ),
    pytest.param(
        rule(
            "crm",
            "customers",
            "customer_type",
            "distribution_drift",
            params=DqParameters(statistic="null_rate"),
            threshold=0.5,
        ),
        ("UPDATE customers SET customer_type = NULL WHERE id % 10 = 0",),
        id="drift_null_rate",
    ),
    pytest.param(
        rule(
            "ecommerce",
            "orders",
            "paid_amount",
            "distribution_drift",
            params=DqParameters(statistic="psi"),
            threshold=0.25,
            max_rows=LARGE_TABLE_SCAN,
        ),
        ("UPDATE orders SET paid_amount = paid_amount + 3000 WHERE id % 3 = 0",),
        id="drift_psi_adaptive_bins",
    ),
)


@pytest.mark.parametrize(("definition", "defects"), HISTORICAL_CASES)
def test_historical_rules_learn_clean_baseline_and_flag_injected_shift(
    pristine: EnterpriseSample,
    tmp_path: Path,
    definition: DqRule,
    defects: tuple[str, ...],
) -> None:
    """Three clean observations form the baseline; an unchanged day passes, a shift fails."""
    clean = source_copy(pristine, definition.target.source_id, tmp_path / "clean")
    history = baseline(definition, clean)
    steady = execute_rule(definition, clean, history, REFERENCE)
    assert (steady.status, steady.actual_value) == ("passed", 0)
    shifted = source_copy(pristine, definition.target.source_id, tmp_path / "shifted")
    inject(shifted, *defects)
    drifted = execute_rule(definition, shifted, history, REFERENCE)
    assert drifted.status == "failed"
    assert drifted.actual_value is not None
    assert drifted.actual_value > definition.threshold


def test_sql_assertion_on_sample_rejects_writes_and_multiple_statements(
    pristine: EnterpriseSample, tmp_path: Path
) -> None:
    """Assertions stay read-only on real sample data: nothing is changed by rejected SQL."""
    source = source_copy(pristine, "ecommerce", tmp_path)
    for sql in (
        "UPDATE orders SET paid_amount = 0",
        "SELECT id FROM orders; DELETE FROM orders",
        "DROP TABLE orders",
    ):
        definition = rule(
            "ecommerce", "orders", None, "sql_assertion", params=DqParameters(sql=sql)
        )
        assert execute_rule(definition, source, now=REFERENCE).status == "error"
    path = (source.connection_url or "").removeprefix("sqlite:///")
    with sqlite3.connect(path) as connection:
        count, total = connection.execute(
            "SELECT count(*), sum(paid_amount) FROM orders"
        ).fetchone()
    assert count == 18000
    assert total > 0
