# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Timezone, epoch and invalid-time regressions using generated fixtures."""

from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.table.io import read_table
from datakeel.operators.timeseries.models import TimestampSummary
from datakeel.operators.timeseries.timestamp_normalize import OPERATOR


def test_mixed_timestamp_forms_normalize_with_original_evidence(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Equivalent epochs and ISO offsets share one UTC millisecond value."""
    file = table_file(
        [
            (value, "a")
            for value in (
                "2026-01-01T00:00:00Z",
                "2026-01-01T08:00:00+08:00",
                "1767225600",
                "1767225600000",
                "2026-01-01T00:00:00",
                "bad",
            )
        ],
        ("timestamp", "device_id"),
    )
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    assert [row[0] for row in read_table(output).rows] == ["1767225600000"] * 5 + [""]
    summary = TimestampSummary.model_validate(output.metadata["timeseries"]["timestamp_normalize"])
    assert summary.invalid_count == 1
    assert {issue.rule for issue in summary.issues} == {"invalid_timestamp", "timezone_mixed"}
    assert next(issue for issue in summary.issues if issue.rule == "invalid_timestamp").rows == (7,)
    assert "epoch_ms" in summary.formats
    assert "declared timezone UTC" in summary.inference_basis


def test_declared_naive_timezone_is_used(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """A caller's source timezone determines the UTC instant without locale guessing."""
    file = table_file([("2026-01-01T08:00:00", "a")], ("timestamp", "device_id"))
    output = OPERATOR.run([file], tmp_path / "out", {"naive_timezone": "Asia/Shanghai"}).files[0]
    assert read_table(output).rows[0][0] == "1767225600000"


def test_invalid_timezone_is_configuration_error(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Invalid timezone configuration fails even when all rows have explicit offsets."""
    file = table_file([("2026-01-01T00:00:00Z", "a")], ("timestamp", "device_id"))
    with pytest.raises(ValidationError, match="Unknown naive_timezone"):
        OPERATOR.run([file], tmp_path / "out", {"naive_timezone": "Invalid/Zone"})


def test_timezone_variation_between_devices_is_not_mixed(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Independent devices may consistently emit different offset encodings."""
    file = table_file(
        [("2026-01-01T00:00:00Z", "a"), ("2026-01-01T08:00:00+08:00", "b")],
        ("timestamp", "device_id"),
    )
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    assert output.metadata["timeseries"]["timestamp_normalize"]["issues"] == []
