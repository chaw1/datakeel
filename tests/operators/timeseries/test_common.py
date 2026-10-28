# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared table/time boundaries retain strict columns and cumulative summaries."""

from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.table.io import read_table
from datakeel.operators.timeseries.common import column_index, numeric_columns, points
from datakeel.operators.timeseries.gaps import OPERATOR as GAPS
from datakeel.operators.timeseries.models import TimeParams
from datakeel.operators.timeseries.order_dedup import OPERATOR as ORDER
from datakeel.operators.timeseries.timestamp_normalize import OPERATOR as NORMALIZE


def test_chained_measurements_preserve_source_rows_and_prior_summaries(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Sorting and later metadata annotation do not erase normalization or source evidence."""
    file = table_file(
        [
            ("2026-01-01T00:00:05Z", "a"),
            ("2026-01-01T00:00:00Z", "a"),
            ("2026-01-01T00:00:01Z", "a"),
        ],
        ("timestamp", "device_id"),
    )
    normalized = NORMALIZE.run([file], tmp_path / "normalize").files[0]
    ordered = ORDER.run([normalized], tmp_path / "order").files[0]
    output = GAPS.run([ordered], tmp_path / "gaps", {"expected_interval_ms": 1000}).files[0]
    assert set(output.metadata["timeseries"]) == {"timestamp_normalize", "order_dedup", "gaps"}
    assert output.metadata["timeseries"]["gaps"]["intervals"][0]["rows"] == [4, 2]


def test_unknown_columns_fail_at_the_declared_boundary(table_file: Callable[..., FileItem]) -> None:
    """A typo in an explicit signal name never silently disables a requested analysis."""
    file = table_file([("0", "a", "10")], ("timestamp", "device_id", "temperature"))
    data = read_table(file)
    with pytest.raises(ValidationError, match="Unknown table column"):
        column_index(data, "missing")
    with pytest.raises(ValidationError, match="Unknown table column"):
        numeric_columns(data, TimeParams(), ["missing"])


def test_invalid_timestamp_remains_a_source_located_issue(
    table_file: Callable[..., FileItem],
) -> None:
    """Downstream operators cannot silently discard invalid normalized timestamps."""
    file = table_file([("bad", "a")], ("timestamp", "device_id"))
    items, issues = points(read_table(file), TimeParams())
    assert items == []
    assert issues[0].rows == (2,)
