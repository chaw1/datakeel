# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Signal-based anomaly regressions include clean controls and independent devices."""

import math
from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.timeseries.anomaly import OPERATOR
from datakeel.operators.timeseries.models import AnomalySummary


def test_anomaly_finds_stuck_spike_jump_and_declared_range(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A fresh synthetic signal exercises every rule without relying on demo values."""
    values = [float(index % 5 + 20) for index in range(41)]
    values[8:15] = [22.5] * 7
    values[30] = 300
    file = table_file(
        [(str(index * 1000), "a", str(value)) for index, value in enumerate(values)],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "value_columns": ["temperature"],
            "window": 11,
            "jump_threshold": 50,
            "ranges": [{"column": "temperature", "minimum": 0, "maximum": 100}],
        },
    ).files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    assert {issue.rule for issue in summary.issues} == {
        "stuck_value",
        "jump",
        "out_of_range",
        "robust_z",
    }
    stuck = next(issue for issue in summary.issues if issue.rule == "stuck_value")
    assert stuck.rows == tuple(range(10, 17))
    outlier = next(issue for issue in summary.issues if issue.rule == "robust_z")
    assert outlier.rows == (32,)
    assert outlier.window == 11
    assert outlier.threshold == 6


def test_normal_smooth_signal_has_no_false_positives(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Ordinary varying temperature and fan-speed readings remain clean."""
    file = table_file(
        [
            (str(index * 1000), "a", str(45 + math.sin(index / 8)), str(200 + index / 10))
            for index in range(200)
        ],
        ("timestamp", "device_id", "temperature", "fan_speed"),
    )
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    assert output.metadata["timeseries"]["anomaly"]["issues"] == []


def test_constant_sensor_is_inferred_but_switch_and_identifier_are_excluded(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """An entirely stuck continuous sensor is distinguishable from categorical controls."""
    file = table_file(
        [(str(index), "a", "30", "1", "7") for index in range(8)],
        ("timestamp", "device_id", "temperature", "switch", "record_id"),
    )
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    assert summary.value_columns == ("temperature",)
    assert [issue.rule for issue in summary.issues] == ["stuck_value"]


def test_no_jump_across_device_boundary(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Different normal baselines in independent devices never create boundary jumps."""
    file = table_file(
        [
            (str(index), device, str(base + index))
            for device, base in [("a", 10), ("b", 1000)]
            for index in range(10)
        ],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run([file], tmp_path / "out", {"jump_threshold": 10}).files[0]
    assert output.metadata["timeseries"]["anomaly"]["issues"] == []


def test_zero_mad_spike_is_detected_without_marking_constant_neighbors(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A localized spike on a constant baseline is still a robust statistical outlier."""
    file = table_file(
        [(str(index), "a", "100" if index == 10 else "20") for index in range(21)],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run([file], tmp_path / "out", {"stuck_min_points": 30}).files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    outliers = [issue.rows for issue in summary.issues if issue.rule == "robust_z"]
    assert outliers == [(12,)]


def test_short_and_nonfinite_signal_has_no_statistical_outlier(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Insufficient numeric evidence does not generate a statistical claim."""
    file = table_file(
        [("0", "a", "1"), ("1", "a", "NaN"), ("2", "a", "2")],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run([file], tmp_path / "out", {"value_columns": ["temperature"]}).files[0]
    assert output.metadata["timeseries"]["anomaly"]["issues"] == []


def test_declared_lower_range_is_checked_without_explicit_value_selection(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A declared bound selects its signal even when automatic inference excludes a small domain."""
    file = table_file([("0", "a", "-10")], ("timestamp", "device_id", "signal"))
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "ranges": [{"column": "signal", "minimum": 0}],
        },
    ).files[0]
    issue = output.metadata["timeseries"]["anomaly"]["issues"][0]
    assert (issue["rule"], issue["threshold"], issue["rows"]) == ("out_of_range", 0, [2])


def test_overlapping_rule_findings_count_one_actual_anomaly_interval(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A single spike may violate multiple rules while representing one abnormal time interval."""
    file = table_file(
        [
            (str(index * 1000), "a", "200" if index == 10 else str(20 + index / 100))
            for index in range(21)
        ],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "value_columns": ["temperature"],
            "ranges": [{"column": "temperature", "maximum": 100}],
        },
    ).files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    assert {issue.rule for issue in summary.issues} == {"robust_z", "out_of_range"}
    assert summary.anomaly_intervals == 1


@pytest.mark.parametrize("missing", ["", "NaN", "inf", "-inf"])
def test_missing_or_nonfinite_samples_break_stuck_windows(
    table_file: Callable[..., FileItem], tmp_path: Path, missing: str
) -> None:
    """Unknown readings cannot join two short constant runs into a claimed stuck interval."""
    file = table_file(
        [(str(index * 1000), "a", missing if index == 4 else "30") for index in range(9)],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    assert output.metadata["timeseries"]["anomaly"]["issues"] == []


def test_sampling_gap_breaks_stuck_and_jump_windows(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Discontinuous samples do not prove one long stuck interval or an immediate jump."""
    file = table_file(
        [
            (str(index * 1000), "a", str(30 if index < 10 else 300))
            for index in (0, 1, 2, 3, 100, 101, 102, 103)
        ],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run([file], tmp_path / "out", {"jump_threshold": 50}).files[0]
    assert output.metadata["timeseries"]["anomaly"]["issues"] == []
