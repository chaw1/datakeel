# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Device-specific ordering, deduplication and source-coordinate regressions."""

from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.table.io import read_table
from datakeel.operators.timeseries.models import OrderSummary
from datakeel.operators.timeseries.order_dedup import OPERATOR


@pytest.mark.parametrize(("keep", "retained"), [("first", "first"), ("last", "last")])
def test_dedup_keeps_declared_row_and_original_coordinates(
    table_file: Callable[..., FileItem], tmp_path: Path, keep: str, retained: str
) -> None:
    """The duplicate key includes device, and transformations retain source row numbers."""
    file = table_file(
        [
            ("2000", "a", "later"),
            ("1000", "a", "first"),
            ("1000", "a", "last"),
            ("1000", "b", "other"),
            ("bad", "a", "invalid"),
        ],
        ("timestamp", "device_id", "value"),
    )
    output = OPERATOR.run([file], tmp_path / "out", {"keep": keep}).files[0]
    data = read_table(output)
    assert data.rows == (
        ("1000", "a", retained),
        ("2000", "a", "later"),
        ("1000", "b", "other"),
        ("bad", "a", "invalid"),
    )
    assert data.row_numbers == ((3 if keep == "first" else 4), 2, 5, 6)
    summary = OrderSummary.model_validate(output.metadata["timeseries"]["order_dedup"])
    assert (summary.out_of_order_count, summary.duplicate_count) == (1, 1)
    assert summary.retained_count == 4


def test_single_group_without_device_column(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Device-less tables can explicitly request one global timestamp partition."""
    file = table_file([("2",), ("1",)], ("timestamp",))
    output = OPERATOR.run([file], tmp_path / "out", {"device_column": None}).files[0]
    assert read_table(output).rows == (("1",), ("2",))


def test_duplicate_that_also_decreases_time_reports_both_rules(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A duplicate-key finding must not mask an independently observed ordering defect."""
    file = table_file([("1000", "a"), ("2000", "a"), ("1000", "a")], ("timestamp", "device_id"))
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    summary = OrderSummary.model_validate(output.metadata["timeseries"]["order_dedup"])
    assert {issue.rule for issue in summary.issues} == {"duplicate_timestamp", "out_of_order"}
    assert (summary.out_of_order_count, summary.duplicate_count) == (1, 1)
