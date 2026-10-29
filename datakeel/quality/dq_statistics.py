# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Constant-space column statistics, including database-sorted adaptive PSI boundaries."""

import math
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise

from sqlglot import exp

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqMetrics, DqQueryLimits, DqRule
from datakeel.core.errors import ExecutionError
from datakeel.core.metric_models import Scalar
from datakeel.metrics.execution import stream_query
from datakeel.quality.dq_evaluation import validate_distribution_values
from datakeel.quality.dq_source import (
    compile_rule_query,
    iter_rule_values,
    source_dialect,
    whole_number,
)
from datakeel.quality.dq_types import nulls_only


@dataclass
class ColumnStatistics:
    """Accumulate scaled online moments and fixed histogram buckets without retaining cells."""

    edges: tuple[float, ...] = ()
    rows: int = 0
    nulls: int = 0
    numbers: int = 0
    scale: float = 0
    mean: float = 0
    moment: float = 0
    buckets: list[int] = field(default_factory=list[int])

    def add(self, values: tuple[Scalar, ...]) -> None:
        """Update bounded statistics from a single batch."""
        if not self.buckets:
            self.buckets = [0] * (len(self.edges) + 1)
        self.rows += len(values)
        self.nulls += sum(value is None for value in values)
        for value in values:
            if (
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and math.isfinite(value)
            ):
                self._number(float(value))

    def _number(self, value: float) -> None:
        if abs(value) > self.scale:
            factor = self.scale / abs(value)
            self.mean *= factor
            self.moment *= factor * factor
            self.scale = abs(value)
        scaled = value / self.scale if self.scale else 0.0
        self.numbers += 1
        delta = scaled - self.mean
        self.mean += delta / self.numbers
        self.moment += delta * (scaled - self.mean)
        self.buckets[bisect_right(self.edges, value)] += 1

    def metrics(self, *, null_only: bool = False) -> DqMetrics:
        """Freeze complete, non-sensitive metrics after the stream has finished."""
        mean = self.mean * self.scale if self.numbers and not null_only else None
        stddev = (
            math.sqrt(max(0, self.moment) / self.numbers) * self.scale if self.numbers else None
        )
        if stddev is not None and not math.isfinite(stddev):
            msg = "Numeric quality statistics exceed finite representation"
            raise ExecutionError(msg)
        return DqMetrics(
            row_count=self.rows,
            mean=mean,
            stddev=None if null_only else stddev,
            null_rate=self.nulls / self.rows if self.rows else 0,
            histogram=()
            if null_only
            else tuple(
                bucket / self.numbers if self.numbers else 0 for bucket in (self.buckets or [0])
            ),
            bin_edges=() if null_only else self.edges,
        )


def collect_statistics(
    rule: DqRule, batches: Iterable[tuple[Scalar, ...]], edges: tuple[float, ...] = ()
) -> ColumnStatistics:
    """Validate every batch before admitting its values into a historical observation."""
    state = ColumnStatistics(edges=edges)
    for values in batches:
        validate_distribution_values(rule, values)
        state.add(values)
    return state


def distribution_metrics(
    rule: DqRule, source: SourceProperties, edges: tuple[float, ...] | None
) -> DqMetrics:
    """Stream moments and, for a cold adaptive PSI baseline, exact database-sorted deciles."""
    if edges is None:
        return _adaptive_metrics(rule, source)
    state = collect_statistics(rule, iter_rule_values(rule, source), edges)
    return state.metrics(null_only=nulls_only(rule))


def _adaptive_metrics(rule: DqRule, source: SourceProperties) -> DqMetrics:
    column = exp.column(rule.target.column or "", quoted=True)
    query = (
        exp.select(column, exp.Window(this=exp.Count(this=column.copy())))
        .from_(exp.table_(rule.target.table, db=rule.target.schema_name, quoted=True))
        .order_by(column.copy())
    )
    state = ColumnStatistics()
    boundaries: dict[float, int] = {}
    position = group_start = 0
    previous: float | None = None
    for batch in stream_query(
        source.connection_url or "",
        compile_rule_query(rule, source, query.sql(dialect=source_dialect(source))),
        DqQueryLimits(timeout_ms=rule.timeout_ms, max_rows=rule.max_rows),
    ):
        values = tuple(row[0] for row in batch.rows)
        validate_distribution_values(rule, values)
        positions = {whole_number(batch.rows[0][1]) * decile // 10 for decile in range(1, 10)}
        for value in values:
            if isinstance(value, int | float):
                number = float(value)
                if number != previous:
                    group_start = position
                if position in positions:
                    boundaries[number] = group_start
                position += 1
                previous = number
        state.add(values)
    edges = tuple(sorted(boundaries))
    ranks = [0, *(boundaries[edge] for edge in edges), state.numbers]
    state.edges = edges
    state.buckets = [end - start for start, end in pairwise(ranks)]
    return state.metrics()
