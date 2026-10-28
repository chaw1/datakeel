# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read monitored quality rules, trends, histories and accountable incidents."""

from typing import Annotated

from fastapi import APIRouter, Query

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.dq_models import DqResult
from datakeel.core.dq_monitor import DqIssue, DqRuleHistory, DqRun
from datakeel.core.dq_views import DqReport, DqRuleView, DqSummary
from datakeel.storage import dq_reads, dq_views
from datakeel.storage.dq_reads import get_run

router = APIRouter(prefix="/api/quality", tags=["quality-rules"])


@router.get("/rules")
def rules(
    db: DatabaseDependency,
    source_id: str | None = None,
    table: str | None = None,
    schema_name: str | None = None,
) -> tuple[DqRuleView, ...]:
    """List exact current definitions with the latest result of each revision."""
    return dq_views.read_rule_views(db, source_id, table, schema_name)


@router.get("/summary")
def summary(
    db: DatabaseDependency,
    source_id: str | None = None,
    table: str | None = None,
    schema_name: str | None = None,
) -> DqSummary:
    """Score current evidence without treating missing history as a pass."""
    return dq_views.read_summary(db, source_id, table, schema_name)


@router.get("/report")
def report(
    db: DatabaseDependency,
    source_id: str | None = None,
    table: str | None = None,
    schema_name: str | None = None,
) -> DqReport:
    """Explain table quality using persisted observations and deterministic prose."""
    return dq_views.read_report(db, source_id, table, schema_name)


@router.get("/issues")
def issues(db: DatabaseDependency, rule_id: str | None = None) -> tuple[DqIssue, ...]:
    """Read merged failure episodes, recovery, ownership and resolution."""
    return dq_reads.read_issues(db, rule_id)


@router.get("/runs/{run_id}")
def run(run_id: str, db: DatabaseDependency) -> DqRun:
    """Read the durable task and terminal result identity for a scheduled execution."""
    with db.session() as session:
        return get_run(session, run_id)


@router.get("/rules/{rule_id}")
def rule(rule_id: str, db: DatabaseDependency) -> DqRuleView:
    """Read a rule definition and the exact revision's latest observation."""
    return dq_views.read_rule_view(db, rule_id)


@router.get("/rules/{rule_id}/results")
def results(
    rule_id: str,
    db: DatabaseDependency,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> tuple[DqResult, ...]:
    """Read a bounded newest-first trend, including observations of older revisions."""
    return dq_reads.read_results(db, rule_id, limit)


@router.get("/rules/{rule_id}/history")
def history(rule_id: str, db: DatabaseDependency) -> tuple[DqRuleHistory, ...]:
    """Read append-only accepted rule revisions, including a deletion tombstone."""
    return dq_reads.read_history(db, rule_id)
