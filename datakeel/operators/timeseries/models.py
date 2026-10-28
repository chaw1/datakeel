# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed parameters and evidence summaries shared by time-series operators."""

from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import Record
from datakeel.operators.base import Params


class TimeParams(Params):
    """Name the timestamp and optional device partition columns."""

    time_column: str = Field(default="timestamp", min_length=1)
    device_column: str | None = "device_id"


class TimestampParams(TimeParams):
    """Normalize timestamps with an explicit assumption for naive local times."""

    naive_timezone: str = Field(default="UTC", min_length=1)
    numeric_unit: Literal["auto", "s", "ms"] = "auto"


class OrderParams(TimeParams):
    """Select the row retained at a duplicate device/timestamp key."""

    keep: Literal["first", "last"] = "first"


class GapsParams(TimeParams):
    """Detect missing samples against a fixed or per-device median interval."""

    expected_interval_ms: int | None = Field(default=None, ge=1)
    tolerance: float = Field(default=1.5, gt=1)


class ResampleParams(TimeParams):
    """Aggregate numeric values in UTC-aligned fixed-width buckets."""

    interval_ms: int = Field(default=60000, ge=1)
    aggregation: Literal["mean", "sum", "min", "max", "first", "last"] = "mean"
    value_columns: list[str] = Field(default_factory=list)


class ColumnRange(Params):
    """Declare an inclusive physical range for a numeric signal."""

    column: str = Field(min_length=1)
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def bounds(self) -> "ColumnRange":
        """Reject inverted ranges."""
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            msg = "minimum must not exceed maximum"
            raise ValidationError(msg)
        return self


class AnomalyParams(TimeParams):
    """Apply independent, declared statistical rules to sensor signals."""

    value_columns: list[str] = Field(default_factory=list)
    window: int = Field(default=11, ge=3, le=1001)
    noise_floor: bool = True
    robust_z_threshold: float = Field(default=6.0, gt=0)
    stuck_min_points: int = Field(default=5, ge=3)
    jump_threshold: float | None = Field(default=None, gt=0)
    ranges: list[ColumnRange] = Field(default_factory=list[ColumnRange])


class UnitDeclaration(ColumnRange):
    """Declare the expected unit without requesting implicit conversion."""

    unit: str = Field(min_length=1)


class UnitParams(TimeParams):
    """Check explicit cell suffixes and ranges against column declarations."""

    declarations: list[UnitDeclaration] = Field(default_factory=list[UnitDeclaration])


class SeriesIssue(Record):
    """Locate one rule failure in original source rows and a UTC interval."""

    rule: str
    column: str
    device: str = ""
    rows: tuple[int, ...]
    start_ms: int | None = None
    end_ms: int | None = None
    threshold: float | None = None
    window: int = 1
    observed: float | None = None
    detail: str
    recommendation: str
    severity: Literal["warning"] = "warning"


class SeriesSummary(Record):
    """Preserve the common evidence envelope across chained operators."""

    row_count: int
    issues: tuple[SeriesIssue, ...] = ()


class TimestampSummary(SeriesSummary):
    """Describe observed timestamp encodings and timezone assumptions."""

    formats: tuple[str, ...]
    timezones: tuple[str, ...]
    inference_basis: str
    invalid_count: int


class OrderSummary(SeriesSummary):
    """Measure source ordering and duplicate keys before remediation."""

    out_of_order_count: int
    duplicate_count: int
    retained_count: int
    keep: Literal["first", "last"]


class GapInterval(Record):
    """Identify a missing-sample interval bounded by observed source rows."""

    device: str
    start_ms: int
    end_ms: int
    gap_ms: int
    expected_interval_ms: int
    missing_samples: int
    rows: tuple[int, int]


class GapsSummary(SeriesSummary):
    """Report per-device gap intervals and total missing-sample duration."""

    intervals: tuple[GapInterval, ...]
    total_gap_ms: int


class ResampleBucket(Record):
    """Retain every original observation represented by an aggregated output bucket."""

    device: str
    start_ms: int
    end_ms: int
    rows: tuple[int, ...]


class ResampleSummary(SeriesSummary):
    """Record the selected fixed-frequency aggregation policy."""

    interval_ms: int
    aggregation: str
    input_rows: int
    output_rows: int
    value_columns: tuple[str, ...]
    buckets: tuple[ResampleBucket, ...] = ()


class AnomalySummary(SeriesSummary):
    """Record anomalous intervals and the columns actually inspected."""

    anomaly_intervals: int
    value_columns: tuple[str, ...]


class UnitSummary(SeriesSummary):
    """Record unit declarations and explicit observed suffixes."""

    declarations: tuple[UnitDeclaration, ...]
    observed_units: tuple[str, ...]
