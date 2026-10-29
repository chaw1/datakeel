# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Question time groups retain native SQL safety and agree with independent bucket sums."""

from datetime import UTC, datetime
from typing import Literal

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import CompileRequest, MetricCard, SemanticLayer
from datakeel.metrics.compiler import compile_metric
from datakeel.metrics.sql_safety import validate_select
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize("grain", ["day", "month", "quarter", "year"])
@pytest.mark.parametrize("dialect", ["sqlite", "postgres"])
def test_native_time_group_compilation_remains_registered_and_read_only(
    layer: SemanticLayer,
    grain: Literal["day", "month", "quarter", "year"],
    dialect: Literal["sqlite", "postgres"],
) -> None:
    """Each backend constructs ISO bucket labels without accepting raw SQL fragments."""
    metric = layer.metrics[0]
    query = compile_metric(
        MetricCard(definition=metric),
        layer.dimensions,
        CompileRequest(time_grain=grain, dialect=dialect),
    )
    assert '"time_bucket"' in query.sql
    assert "GROUP BY" in query.sql
    assert metric.time.column in query.columns
    assert validate_select(query.sql, dialect)
    if dialect == "postgres":
        assert "DATE_TRUNC" in query.sql
        assert "TO_CHAR" in query.sql
    else:
        assert "STRFTIME" in query.sql or "DATE(" in query.sql


@pytest.mark.parametrize("group", ["按天", "按月", "按季度", "按年"])
def test_generated_time_buckets_sum_to_the_equivalent_scalar_query(
    db: Database, enterprise_sample: EnterpriseSample, group: str
) -> None:
    """Calendar grouping changes only the output shape, retaining the same source data."""
    grouped = ask_data(
        db, AskRequest(question=f"上个季度华东零售额{group}", reference_instant=REFERENCE)
    )
    scalar = ask_data(db, AskRequest(question="上个季度华东零售额", reference_instant=REFERENCE))
    assert grouped.status == scalar.status == "answered"
    assert grouped.result
    assert scalar.result
    assert grouped.result.columns == ["time_bucket", "value"]
    values = [row[-1] for row in grouped.result.rows]
    assert all(isinstance(value, int | float) for value in values)
    assert sum(float(str(value)) for value in values) == pytest.approx(scalar.result.rows[0][0])
