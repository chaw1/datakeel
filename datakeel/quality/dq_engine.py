# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute immutable quality rules through existing bounded read-only connections."""

from datetime import UTC, datetime
from statistics import fmean
from time import monotonic

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqMetrics, DqResult, DqRule, DqSample
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.metric_models import Scalar
from datakeel.core.models import utcnow
from datakeel.quality.dq_evaluation import (
    decile_edges,
    observation,
    population_stability,
    relative_change,
    stable_mean,
    validate_distribution_values,
    violating_rows,
)
from datakeel.quality.dq_regex import regex_violations
from datakeel.quality.dq_source import (
    TableAggregate,
    execute_assertion,
    read_rule_table,
    read_table_aggregate,
)
from datakeel.quality.dq_types import nulls_only


def execute_rule(
    rule: DqRule,
    source: SourceProperties,
    history: tuple[DqResult, ...] = (),
    now: datetime | None = None,
) -> DqResult:
    """Evaluate one rule with an injected UTC clock and successful historical observations."""
    instant = now or utcnow()
    if instant.tzinfo is None:
        msg = "Quality execution requires an aware clock"
        raise ValidationError(msg)
    started = monotonic()
    deadline = started + rule.timeout_ms / 1000
    try:
        result = _evaluate(rule, source, history, instant.astimezone(UTC), deadline)
        _remaining(rule, deadline)
    except (ExecutionError, ValidationError) as error:
        result = DqResult(
            rule_id=rule.id,
            rule_revision=rule.revision,
            status="error",
            threshold=rule.threshold,
            started_at=instant,
            message=str(error),
        )
    return result.model_copy(update={"duration_ms": (monotonic() - started) * 1000})


def _evaluate(
    rule: DqRule,
    source: SourceProperties,
    history: tuple[DqResult, ...],
    now: datetime,
    deadline: float,
) -> DqResult:
    if rule.kind == "sql_assertion":
        rows = execute_assertion(_remaining(rule, deadline), source)
        failed = tuple(range(1, len(rows.rows) + 1))
        return _result(rule, now, DqMetrics(row_count=len(rows.rows)), failed, float(len(failed)))
    if rule.kind in {"volume_change", "freshness"}:
        aggregate = read_table_aggregate(_remaining(rule, deadline), source)
        if rule.kind == "freshness":
            return _freshness(rule, aggregate, now)
        metrics = DqMetrics(row_count=aggregate.row_count)
        return _historical(rule, metrics, _baseline(rule, history, now), now)
    rows = read_rule_table(_remaining(rule, deadline), source)
    values = tuple(row[0] for row in rows.rows)
    validate_distribution_values(rule, values)
    baseline = _baseline(rule, history, now)
    metrics = observation(values, _histogram_edges(rule, baseline, values))
    if nulls_only(rule):
        # NULL-only scans project markers, so no business value statistics exist.
        metrics = DqMetrics(row_count=metrics.row_count, null_rate=metrics.null_rate)
    if rule.kind == "distribution_drift":
        return _historical(rule, metrics, baseline, now)
    reference = ()
    if rule.params.reference_table:
        reference = tuple(
            row[0]
            for row in read_rule_table(_remaining(rule, deadline), source, reference=True).rows
        )
    failed = (
        regex_violations(rule.params.pattern or "", values, _remaining(rule, deadline).timeout_ms)
        if rule.kind == "regex"
        else violating_rows(rule, values, reference)
    )
    actual = len(failed) / len(values) if values else 0.0
    return _result(rule, now, metrics, failed, actual)


def _remaining(rule: DqRule, deadline: float) -> DqRule:
    timeout_ms = int((deadline - monotonic()) * 1000)
    if timeout_ms < 1:
        msg = "Quality rule exceeded its execution timeout"
        raise ExecutionError(msg)
    return rule.model_copy(update={"timeout_ms": timeout_ms})


def _result(
    rule: DqRule, now: datetime, metrics: DqMetrics, failed: tuple[int, ...], actual: float
) -> DqResult:
    return DqResult(
        rule_id=rule.id,
        rule_revision=rule.revision,
        status="passed" if actual <= rule.threshold else "failed",
        actual_value=actual,
        threshold=rule.threshold,
        row_count=metrics.row_count,
        failed_count=len(failed),
        metrics=metrics,
        started_at=now,
        samples=tuple(
            DqSample(row_number=index, column=rule.target.column) for index in failed[:5]
        ),
    )


def _freshness(rule: DqRule, aggregate: TableAggregate, now: datetime) -> DqResult:
    metrics = DqMetrics(row_count=aggregate.row_count)
    if aggregate.invalid or aggregate.latest is None:
        return DqResult(
            rule_id=rule.id,
            rule_revision=rule.revision,
            status="failed",
            threshold=rule.threshold,
            row_count=metrics.row_count,
            metrics=metrics,
            started_at=now,
            message=(
                f"{aggregate.invalid} non-NULL cells are not valid timestamps"
                if aggregate.invalid
                else "No valid latest timestamp is available"
            ),
        )
    return _result(rule, now, metrics, (), max(0.0, (now - aggregate.latest).total_seconds()))


def _baseline(rule: DqRule, history: tuple[DqResult, ...], now: datetime) -> list[DqResult]:
    return sorted(
        (
            item
            for item in history
            if item.rule_id == rule.id
            and item.rule_revision == rule.revision
            and item.started_at < now
            and item.status in {"passed", "baseline_insufficient"}
        ),
        key=lambda item: item.started_at,
        reverse=True,
    )[: rule.params.baseline_runs]


def _histogram_edges(
    rule: DqRule, baseline: list[DqResult], values: tuple[Scalar, ...]
) -> tuple[float, ...]:
    if rule.params.bin_edges or rule.kind != "distribution_drift" or rule.params.statistic != "psi":
        return rule.params.bin_edges
    # Adaptive bins are fixed by the revision's first numeric observation and then reused.
    for item in baseline:
        if item.metrics.bin_edges:
            return item.metrics.bin_edges
    return decile_edges(values)


def _historical(
    rule: DqRule, metrics: DqMetrics, recent: list[DqResult], now: datetime
) -> DqResult:
    if len(recent) < rule.params.baseline_runs:
        return DqResult(
            rule_id=rule.id,
            rule_revision=rule.revision,
            status="baseline_insufficient",
            threshold=rule.threshold,
            row_count=metrics.row_count,
            metrics=metrics,
            started_at=now,
            message="Not enough successful historical observations",
        )
    actual = _drift(rule, metrics, tuple(item.metrics for item in recent))
    if actual is None:
        msg = "Distribution comparison requires numeric observations and compatible bins"
        raise ExecutionError(msg)
    return _result(rule, now, metrics, (), actual)


def _drift(rule: DqRule, metrics: DqMetrics, history: tuple[DqMetrics, ...]) -> float | None:
    if rule.kind == "volume_change":
        return relative_change(metrics.row_count, fmean(item.row_count for item in history))
    statistic = rule.params.statistic
    if statistic == "psi":
        if any(item.bin_edges != metrics.bin_edges for item in history):
            return None
        baseline = tuple(
            fmean(bucket) for bucket in zip(*(item.histogram for item in history), strict=True)
        )
        return population_stability(metrics.histogram, baseline)
    current = getattr(metrics, statistic)
    previous = tuple(getattr(item, statistic) for item in history)
    if current is None or any(value is None for value in previous):
        return None
    return relative_change(float(current), stable_mean(tuple(float(value) for value in previous)))
