# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sampling-gap detection respects independent devices and original evidence rows."""

from collections.abc import Callable
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.timeseries.gaps import OPERATOR
from datakeel.operators.timeseries.models import GapsSummary


def test_gaps_detected_per_device_with_total_missing_duration(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Missing duration excludes the expected observed-to-observed sampling interval."""
    file = table_file(
        [("0", "a"), ("1000", "a"), ("5000", "a"), ("0", "b"), ("1000", "b"), ("2000", "b")],
        ("timestamp", "device_id"),
    )
    output = OPERATOR.run([file], tmp_path / "out", {"expected_interval_ms": 1000}).files[0]
    summary = GapsSummary.model_validate(output.metadata["timeseries"]["gaps"])
    assert summary.total_gap_ms == 3000
    assert len(summary.intervals) == 1
    interval = summary.intervals[0]
    assert (interval.device, interval.rows, interval.missing_samples) == ("a", (3, 4), 3)
    assert summary.issues[0].threshold == 1500


def test_median_interval_ignores_duplicates_and_detects_long_gap(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A sparse gap does not change a device's dominant sampling period."""
    file = table_file(
        [(str(value), "a") for value in (0, 1000, 1000, 2000, 6000)], ("timestamp", "device_id")
    )
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    summary = GapsSummary.model_validate(output.metadata["timeseries"]["gaps"])
    assert summary.intervals[0].expected_interval_ms == 1000


def test_single_or_duplicate_only_device_has_no_gap(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """No interval is inferred from fewer than two distinct timestamps."""
    file = table_file([("0", "a"), ("0", "a"), ("10000", "b")], ("timestamp", "device_id"))
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    assert output.metadata["timeseries"]["gaps"]["intervals"] == []
