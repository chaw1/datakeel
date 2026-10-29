# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute immutable quality rules through existing bounded read-only connections."""

from datetime import UTC, datetime
from statistics import fmean
from time import monotonic

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqMetrics, DqResult, DqRule, DqSample
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import utcnow
from datakeel.quality.dq_constraints import count_constraints
from datakeel.quality.dq_evaluation import (
    population_stability,
    relative_change,
    stable_mean,
)
from datakeel.quality.dq_regex import regex_observation
from datakeel.quality.dq_source import (
    TableAggregate,
    execute_assertion,
    read_table_aggregate,
)
from datakeel.quality.dq_statistics import distribution_metrics


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
        result = result.model_copy(
            update={
                "rows_total": result.rows_total
                if result.rows_total is not None
                else result.row_count,
                "rows_scanned": result.rows_total
                if result.rows_total is not None
                else result.row_count,
                "coverage": "complete",
            }
        )
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
        observation = execute_assertion(_remaining(rule, deadline), source)
        failed = tuple(range(1, len(observation.result.rows) + 1))
        return _result(
            rule, now, DqMetrics(row_count=len(observation.result.rows)), failed, float(len(failed))
        ).model_copy(update={"rows_total": observation.rows_total})
    if rule.kind in {"volume_change", "freshness"}:
        aggregate = read_table_aggregate(_remaining(rule, deadline), source)
        if rule.kind == "freshness":
            return _freshness(rule, aggregate, now)
        metrics = DqMetrics(row_count=aggregate.row_count)
        return _historical(rule, metrics, _baseline(rule, history, now), now)
    baseline = _baseline(rule, history, now)
    if rule.kind == "distribution_drift":
        metrics = distribution_metrics(
            _remaining(rule, deadline), source, _histogram_edges(rule, baseline)
        )
        return _historical(rule, metrics, baseline, now)
    if rule.kind == "regex":
        observation = regex_observation(_remaining(rule, deadline), source)
        metrics, failed, samples = (
            observation.metrics,
            observation.failed_count,
            observation.samples,
        )
    else:
        counts = count_constraints(_remaining(rule, deadline), source)
        metrics = DqMetrics(
            row_count=counts.rows,
            null_rate=counts.nulls / counts.rows if counts.rows else 0,
            mean=counts.mean,
            stddev=counts.stddev,
        )
        failed = counts.failed
        samples = (counts.first_failure,) if counts.first_failure is not None else ()
    actual = failed / metrics.row_count if metrics.row_count else 0.0
    return _result(rule, now, metrics, samples, actual).model_copy(update={"failed_count": failed})


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


def _histogram_edges(rule: DqRule, baseline: list[DqResult]) -> tuple[float, ...] | None:
    if rule.params.bin_edges or rule.params.statistic != "psi":
        return rule.params.bin_edges
    for item in baseline:
        if item.metrics.bin_edges:
            return item.metrics.bin_edges
    return None


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
            stable_mean(bucket)
            for bucket in zip(*(item.histogram for item in history), strict=True)
        )
        return population_stability(metrics.histogram, baseline)
    current = getattr(metrics, statistic)
    previous = tuple(getattr(item, statistic) for item in history)
    if current is None or any(value is None for value in previous):
        return None
    return relative_change(float(current), stable_mean(tuple(float(value) for value in previous)))
