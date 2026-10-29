# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen query frames and measured comparison evidence for question turns."""

from typing import Literal

from datakeel.core.metric_models import (
    CompiledQuery,
    DimensionSlice,
    QueryResult,
    Scalar,
    TimeRange,
)
from datakeel.core.models import BoundaryModel

TimeGrain = Literal["day", "month", "quarter", "year"]
ComparisonMode = Literal["year_over_year", "period_over_period"]


class AskQueryFrame(BoundaryModel):
    """Retain the complete resolved query, independently of conversational phrasing."""

    metric_id: str
    time_range: TimeRange | None = None
    time_basis: Literal["period", "as_of"] | None = None
    slices: tuple[DimensionSlice, ...] = ()
    group_by: tuple[str, ...] = ()
    time_grain: TimeGrain | None = None
    comparison: ComparisonMode | None = None
    share_of_result_rows: bool = False


class ComparisonChange(BoundaryModel):
    """Compare corresponding result rows without substituting a missing baseline."""

    dimensions: tuple[Scalar, ...] = ()
    current_value: float | None = None
    previous_value: float | None = None
    delta: float | None = None
    percent_change: float | None = None


class AskComparison(BoundaryModel):
    """Expose the actual second query result and its arithmetic comparison."""

    mode: ComparisonMode
    previous_time_range: TimeRange
    previous_sql: CompiledQuery
    previous_result: QueryResult
    changes: tuple[ComparisonChange, ...] = ()
