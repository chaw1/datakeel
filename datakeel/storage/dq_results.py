# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomically publish fenced quality results, merged incidents and webhook events."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.dq_monitor import DqAlert, DqCompletion
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.dq_issues import active_status, observe_result
from datakeel.storage.dq_rows import DqResultRow, DqRuleRow, DqRunRow, DqWebhookRow


def publish_completion(session: Session, completion: DqCompletion, task_id: str) -> None:
    """Accept a single result only while its parent task and shard lease are locked."""
    run = session.get(DqRunRow, completion.run_id, with_for_update=True)
    if run is None or run.task_id != task_id:
        msg = "Quality run does not belong to this task"
        raise NotFoundError(msg)
    result = completion.result
    if result.rule_id != run.rule_id or result.rule_revision != run.rule_revision:
        msg = "Quality result does not match its frozen rule"
        raise ConflictError(msg)
    if run.result_id is not None:
        return
    # Serialize incident transitions even when distinct runs finish concurrently.
    current = session.scalar(select(DqRuleRow).where(DqRuleRow.id == run.rule_id).with_for_update())
    latest = session.scalar(
        select(DqResultRow.started_at)
        .where(
            DqResultRow.rule_id == result.rule_id,
            DqResultRow.rule_revision == result.rule_revision,
        )
        .order_by(DqResultRow.started_at.desc())
        .limit(1)
    )
    sequence = (
        session.scalar(
            select(func.max(DqResultRow.sequence)).where(DqResultRow.rule_id == result.rule_id)
        )
        or 0
    )
    session.add(
        DqResultRow(
            id=result.id,
            run_id=run.id,
            rule_id=result.rule_id,
            rule_revision=result.rule_revision,
            status=result.status,
            started_at=result.started_at.timestamp(),
            sequence=sequence + 1,
            payload=result.model_dump(mode="json", exclude={"passed"}),
        )
    )
    run.state, run.result_id = "COMPLETED", result.id
    if (
        current is not None
        and not current.deleted
        and current.payload.get("enabled", True)
        and current.revision == result.rule_revision
        and (latest is None or latest <= result.started_at.timestamp())
    ):
        _incident(session, DqRule.model_validate(run.rule_payload), result)
    session.flush()


def _incident(session: Session, rule: DqRule, result: DqResult) -> None:
    now = utcnow()
    prior = active_status(session, result.rule_id)
    issue = observe_result(session, result, now)
    # Alert on episode transitions only; merged failures just raise the issue's count.
    if issue is None or issue.status == prior:
        return
    event = DqAlert(
        event_id=new_id(),
        event_type="quality.recovered" if result.status == "passed" else "quality.failed",
        issue=issue,
        rule_id=rule.id,
        rule_name=rule.name,
        severity=rule.severity,
        result_id=result.id,
        occurred_at=now,
    )
    session.add(
        DqWebhookRow(
            id=event.event_id,
            body=event.model_dump_json(),
            due_at=now.timestamp(),
            delivered=False,
            attempts=0,
        )
    )


def finish_failed(
    session: Session,
    run_id: str,
    error: str,
    *,
    cancelled: bool = False,
    started_at: datetime | None = None,
) -> None:
    """Record a fenced terminal error once, while cancellation has no quality verdict."""
    run = session.get(DqRunRow, run_id)
    if run is None or run.result_id is not None:
        return
    if cancelled:
        run.state, run.error = "CANCELLED", error
        return
    rule = DqRule.model_validate(run.rule_payload)
    result = DqResult(
        rule_id=rule.id,
        rule_revision=rule.revision,
        status="error",
        threshold=rule.threshold,
        started_at=started_at or utcnow(),
        message="Worker retries exhausted or task failed before publication",
    )
    publish_completion(session, DqCompletion(run_id=run.id, result=result), run.task_id)
    run.state, run.error = "FAILED", error
