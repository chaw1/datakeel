# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Merge consecutive quality failures and audit human incident transitions."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.dq_models import DqResult
from datakeel.core.dq_monitor import DqIssue, DqIssueStatus
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.dq_rows import DqIssueAuditRow, DqIssueRow, DqRuleRow


def _view(session: Session, issue: DqIssue) -> DqIssue:
    rule = session.get(DqRuleRow, issue.rule_id)
    retired = rule is not None and (rule.deleted or not rule.payload.get("enabled", True))
    allowed = issue.status != "resolved" and (issue.status == "recovered" or retired)
    return issue.model_copy(update={"can_resolve": allowed})


def get_issue(session: Session, issue_id: str) -> DqIssue:
    """Read a single current incident without leaking mutable persistence rows."""
    row = session.get(DqIssueRow, issue_id)
    if row is None:
        msg = "Quality issue not found"
        raise NotFoundError(msg)
    return _view(session, DqIssue.model_validate(row.payload))


def list_issues(session: Session, rule_id: str | None = None) -> tuple[DqIssue, ...]:
    """List all episodes in deterministic order, including resolved history."""
    query = select(DqIssueRow).order_by(DqIssueRow.id)
    if rule_id is not None:
        query = query.where(DqIssueRow.rule_id == rule_id)
    return tuple(
        _view(session, DqIssue.model_validate(row.payload)) for row in session.scalars(query)
    )


def _persist(session: Session, row: DqIssueRow, issue: DqIssue, actor: str) -> DqIssue:
    row.payload = issue.model_dump(mode="json", exclude={"can_resolve"})
    row.active = issue.status != "resolved"
    session.add(
        DqIssueAuditRow(
            id=new_id(),
            issue_id=issue.id,
            actor=actor,
            occurred_at=issue.updated_at.timestamp(),
            payload=issue.model_dump(mode="json"),
        )
    )
    session.flush()
    return _view(session, issue)


def change_issue(
    session: Session,
    issue_id: str,
    status: DqIssueStatus,
    assignee: str | None,
    expected_revision: int,
    actor: str,
) -> DqIssue:
    """Claim or resolve an incident after comparing its prepared revision."""
    row = session.get(DqIssueRow, issue_id, with_for_update=True)
    if row is None:
        msg = "Quality issue not found"
        raise NotFoundError(msg)
    issue = _view(session, DqIssue.model_validate(row.payload))
    if issue.revision != expected_revision:
        msg = "Quality issue revision changed"
        raise ConflictError(msg)
    if status not in {"claimed", "resolved"} or issue.status == "resolved":
        msg = "Only active quality issues can be claimed or resolved"
        raise ValidationError(msg)
    if status == "resolved" and not issue.can_resolve:
        msg = "Confirm a successful recovery before resolving a quality issue"
        raise ValidationError(msg)
    if status == "claimed" and not assignee:
        msg = "Claiming a quality issue requires an assignee"
        raise ValidationError(msg)
    return _persist(
        session,
        row,
        issue.model_copy(
            update={
                "status": "recovered"
                if issue.status == "recovered" and status == "claimed"
                else status,
                "assignee": assignee or issue.assignee,
                "revision": issue.revision + 1,
                "updated_at": utcnow(),
            }
        ),
        actor,
    )


def active_status(session: Session, rule_id: str) -> DqIssueStatus | None:
    """Read the current episode state before an observation changes it."""
    row = session.scalar(
        select(DqIssueRow).where(DqIssueRow.rule_id == rule_id, DqIssueRow.active.is_(True))
    )
    return DqIssue.model_validate(row.payload).status if row is not None else None


def observe_result(session: Session, result: DqResult, now: datetime) -> DqIssue | None:
    """Merge ongoing failures; mark a passing episode recovered pending confirmation."""
    if result.status not in {"failed", "error", "passed"}:
        return None
    row = session.scalar(
        select(DqIssueRow)
        .where(DqIssueRow.rule_id == result.rule_id, DqIssueRow.active.is_(True))
        .with_for_update()
    )
    if row is None:
        if result.status == "passed":
            return None
        identifier = new_id()
        row = DqIssueRow(id=identifier, rule_id=result.rule_id, active=True)
        session.add(row)
        issue = DqIssue(
            id=identifier,
            rule_id=result.rule_id,
            status="open",
            failures=1,
            first_result_id=result.id,
            last_result_id=result.id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
    else:
        prior = DqIssue.model_validate(row.payload)
        failed = result.status != "passed"
        if not failed and prior.status == "recovered":
            return None
        status = (
            ("open" if prior.status == "recovered" else prior.status) if failed else "recovered"
        )
        issue = prior.model_copy(
            update={
                "status": status,
                "failures": prior.failures + int(failed),
                "last_result_id": result.id,
                "revision": prior.revision + 1,
                "updated_at": now,
            }
        )
    return _persist(session, row, issue, "quality-worker")
