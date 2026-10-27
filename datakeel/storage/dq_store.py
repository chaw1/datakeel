# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Revision-fenced quality rule mutations in the caller's controlled transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.dq_models import DqRule
from datakeel.core.dq_monitor import DqRuleHistory
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.dq_rows import DqHistoryRow, DqRuleRow


def get_rule(session: Session, rule_id: str, *, include_deleted: bool = False) -> DqRule:
    """Read a current rule, optionally including its versioned deletion tombstone."""
    row = session.get(DqRuleRow, rule_id)
    if row is None or (row.deleted and not include_deleted):
        msg = "Quality rule not found"
        raise NotFoundError(msg)
    return DqRule.model_validate(row.payload)


def rule_revision(session: Session, rule_id: str) -> int | None:
    """Expose the persisted revision, including tombstones, for action plan fencing."""
    row = session.get(DqRuleRow, rule_id)
    return row.revision if row is not None else None


def list_rules(session: Session, source_id: str | None = None) -> tuple[DqRule, ...]:
    """List current definitions in stable identifier order."""
    query = select(DqRuleRow).where(DqRuleRow.deleted.is_(False)).order_by(DqRuleRow.id)
    if source_id is not None:
        query = query.where(DqRuleRow.source_id == source_id)
    return tuple(DqRule.model_validate(row.payload) for row in session.scalars(query))


def _history(session: Session, rule: DqRule, actor: str, operation: str) -> None:
    history = DqRuleHistory.model_validate(
        {
            "rule_id": rule.id,
            "revision": rule.revision,
            "operation": operation,
            "actor": actor,
            "rule": rule,
            "occurred_at": utcnow(),
        }
    )
    session.add(
        DqHistoryRow(
            id=new_id(),
            rule_id=rule.id,
            revision=rule.revision,
            payload=history.model_dump(mode="json"),
        )
    )


def upsert_rule(
    session: Session, rule: DqRule, expected_revision: int | None, actor: str
) -> DqRule:
    """Create once or append a revision after verifying the frozen prior revision."""
    row = session.get(DqRuleRow, rule.id, with_for_update=True)
    actual = row.revision if row is not None else None
    if actual != expected_revision:
        msg = "Quality rule revision changed"
        raise ConflictError(msg)
    if row is not None and row.deleted:
        msg = "Deleted quality rule identifiers cannot be reused"
        raise ConflictError(msg)
    rule = DqRule.model_validate(rule.model_copy(update={"revision": (actual or 0) + 1}))
    if row is None:
        row = DqRuleRow(id=rule.id, deleted=False)
        session.add(row)
    row.revision = rule.revision
    row.source_id = rule.target.source_id
    row.payload = rule.model_dump(mode="json")
    _history(session, rule, actor, "create" if actual is None else "update")
    session.flush()
    return rule


def delete_rule(session: Session, rule_id: str, expected_revision: int, actor: str) -> DqRule:
    """Retain a tombstone and history while removing a rule from future scheduling."""
    row = session.get(DqRuleRow, rule_id, with_for_update=True)
    if row is None or row.deleted:
        msg = "Quality rule not found"
        raise NotFoundError(msg)
    if row.revision != expected_revision:
        msg = "Quality rule revision changed"
        raise ConflictError(msg)
    rule = get_rule(session, rule_id).model_copy(update={"revision": row.revision + 1})
    row.revision, row.deleted, row.payload = rule.revision, True, rule.model_dump(mode="json")
    _history(session, rule, actor, "delete")
    session.flush()
    return rule


def rule_history(session: Session, rule_id: str) -> tuple[DqRuleHistory, ...]:
    """Read every accepted definition, including the final deletion snapshot."""
    return tuple(
        DqRuleHistory.model_validate(row.payload)
        for row in session.scalars(
            select(DqHistoryRow)
            .where(DqHistoryRow.rule_id == rule_id)
            .order_by(DqHistoryRow.revision)
        )
    )
