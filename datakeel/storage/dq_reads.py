# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed read facade for quality rules, trends, history, incidents and jobs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.dq_monitor import DqIssue, DqRuleHistory, DqRun
from datakeel.core.errors import NotFoundError
from datakeel.storage.database import Database, ShardRow, TaskRow
from datakeel.storage.dq_issues import list_issues
from datakeel.storage.dq_rows import DqResultRow, DqRunRow
from datakeel.storage.dq_store import list_rules, rule_history


def read_rules(db: Database, source_id: str | None = None) -> tuple[DqRule, ...]:
    """Return current quality definitions, optionally scoped to a source."""
    with db.session() as session:
        return list_rules(session, source_id)


def read_issues(db: Database, rule_id: str | None = None) -> tuple[DqIssue, ...]:
    """Return current and historical incidents, optionally scoped to one rule."""
    with db.session() as session:
        return list_issues(session, rule_id)


def read_history(db: Database, rule_id: str) -> tuple[DqRuleHistory, ...]:
    """Read the accepted definitions for a live or deleted rule."""
    with db.session() as session:
        return rule_history(session, rule_id)


def list_results(
    session: Session,
    rule_id: str,
    limit: int = 100,
    revision: int | None = None,
    *,
    successful_only: bool = False,
) -> tuple[DqResult, ...]:
    """Read newest observations first, with stable ordering for equal timestamps."""
    query = select(DqResultRow).where(DqResultRow.rule_id == rule_id)
    if revision is not None:
        query = query.where(DqResultRow.rule_revision == revision)
    if successful_only:
        query = query.where(DqResultRow.status.in_(("passed", "baseline_insufficient")))
    rows = session.scalars(
        query.order_by(
            DqResultRow.started_at.desc(),
            DqResultRow.sequence.desc().nulls_last(),
            DqResultRow.id.desc(),
        ).limit(max(1, min(limit, 1000)))
    )
    return tuple(DqResult.model_validate(row.payload) for row in rows)


def read_results(db: Database, rule_id: str, limit: int = 100) -> tuple[DqResult, ...]:
    """Read a bounded trend including failures and explicit non-verdict states."""
    with db.session() as session:
        return list_results(session, rule_id, limit)


def get_run(session: Session, run_id: str) -> DqRun:
    """Expose a job's durable task identity and terminal result."""
    row = session.get(DqRunRow, run_id)
    if row is None:
        msg = "Quality run not found"
        raise NotFoundError(msg)
    return DqRun(
        id=row.id,
        rule_id=row.rule_id,
        rule_revision=row.rule_revision,
        slot=row.slot,
        task_id=row.task_id,
        state=_run_state(session, row),
        result_id=row.result_id,
        error=row.error,
    )


def _run_state(session: Session, row: DqRunRow) -> str:
    task = session.get(TaskRow, row.task_id)
    if task is None:
        return row.state
    if task.state == "QUEUED" and session.scalar(
        select(ShardRow.id).where(ShardRow.task_id == task.id, ShardRow.state == "RUNNING").limit(1)
    ):
        return "RUNNING"
    return task.state


def read_execution_inputs(
    db: Database,
    run_id: str,
) -> tuple[DqRule, tuple[DqResult, ...]]:
    """Read a frozen job and its same-revision successful baseline observations."""
    with db.session() as session:
        run = session.get(DqRunRow, run_id)
        if run is None:
            msg = "Quality run not found"
            raise NotFoundError(msg)
        rule = DqRule.model_validate(run.rule_payload)
        history = list_results(
            session,
            rule.id,
            rule.params.baseline_runs,
            rule.revision,
            successful_only=True,
        )
    return rule, history
