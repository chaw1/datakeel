# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed-frequency aggregation uses device partitions and never fills gaps implicitly."""

from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.table.io import read_table
from datakeel.operators.timeseries.resample import OPERATOR


@pytest.mark.parametrize(
    ("method", "value"),
    [
        ("mean", "3"),
        ("sum", "6"),
        ("min", "2"),
        ("max", "4"),
        ("first", "2"),
        ("last", "4"),
    ],
)
def test_resample_aggregations_are_timestamp_sorted_and_device_isolated(
    table_file: Callable[..., FileItem], tmp_path: Path, method: str, value: str
) -> None:
    """UTC-aligned populated buckets use the requested deterministic numeric aggregation."""
    file = table_file(
        [
            ("900", "a", "4", "x"),
            ("100", "a", "2", "y"),
            ("100", "b", "20", "z"),
            ("5000", "a", "8", "x"),
        ],
        ("timestamp", "device_id", "temperature", "event"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "interval_ms": 1000,
            "aggregation": method,
            "value_columns": ["temperature"],
        },
    ).files[0]
    assert read_table(output).rows == (
        ("0", "a", value, ""),
        ("5000", "a", "8", "x"),
        ("0", "b", "20", "z"),
    )
    assert read_table(output).row_numbers == (3, 5, 4)


def test_resample_ignores_nonfinite_values_within_explicit_signal(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Missing/nonfinite samples are not treated as zero during aggregation."""
    file = table_file(
        [("0", "a", "NaN"), ("10", "a", "4")], ("timestamp", "device_id", "temperature")
    )
    output = OPERATOR.run([file], tmp_path / "out", {"value_columns": ["temperature"]}).files[0]
    assert read_table(output).rows[0][2] == "4"


def test_resample_retains_all_bucket_source_coordinates(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A derived mean remains traceable to every original contributing source row."""
    file = table_file(
        [("900", "a", "4"), ("100", "a", "2")], ("timestamp", "device_id", "temperature")
    )
    output = OPERATOR.run(
        [file], tmp_path / "out", {"interval_ms": 1000, "value_columns": ["temperature"]}
    ).files[0]
    bucket = output.metadata["timeseries"]["resample"]["buckets"][0]
    assert bucket == {"device": "a", "start_ms": 0, "end_ms": 1000, "rows": [3, 2]}


def test_empty_bucket_values_remain_missing(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """An observed bucket with no finite signal values is represented by an empty cell."""
    file = table_file([("0", "a", "")], ("timestamp", "device_id", "temperature"))
    output = OPERATOR.run([file], tmp_path / "out", {"value_columns": ["temperature"]}).files[0]
    assert read_table(output).rows[0][2] == ""


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("mean", "9007199254740994"),
        ("sum", "18014398509481988"),
        ("first", "9007199254740993"),
        ("last", "9007199254740995"),
        ("min", "9007199254740993"),
        ("max", "9007199254740995"),
    ],
)
def test_resample_preserves_large_integer_precision(
    table_file: Callable[..., FileItem], tmp_path: Path, method: str, expected: str
) -> None:
    """Counters beyond binary float's exact integer range retain their numeric evidence."""
    file = table_file(
        [("0", "a", "9007199254740993"), ("1", "a", "9007199254740995")],
        ("timestamp", "device_id", "counter"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "value_columns": ["counter"],
            "aggregation": method,
        },
    ).files[0]
    assert read_table(output).rows[0][2] == expected


def test_resample_unknown_columns_fail_instead_of_silently_disabling_signal(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """An explicit nonexistent signal fails before any aggregate artifact is written."""
    file = table_file([("0", "a", "10")], ("timestamp", "device_id", "temperature"))
    with pytest.raises(ValidationError, match="Unknown table column"):
        OPERATOR.run([file], tmp_path / "out", {"value_columns": ["typo"]})
    assert not list((tmp_path / "out").glob("*.csv"))
