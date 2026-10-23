# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional semantic audit records and typed version-history reads."""

from datetime import UTC, datetime

from sqlalchemy import Float, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from datakeel.actions.models import ActionPlan
from datakeel.core.metric_history_models import MetricAudit, MetricHistory
from datakeel.core.metric_models import MetricMutation
from datakeel.core.models import new_id, utcnow
from datakeel.storage.base import Base


class MetricAuditRow(Base):
    """Keep a semantic change's exact actor and version transition queryable."""

    __tablename__ = "metric_audit"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), index=True)
    actor: Mapped[str] = mapped_column(String)
    metric_id: Mapped[str] = mapped_column(String, index=True)
    from_version: Mapped[int] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String)
    action_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())


def record_metric_audit(session: Session, plan: ActionPlan, change: MetricMutation) -> None:
    """Commit audit in the same transaction as the semantic event and action receipt."""
    session.add(
        MetricAuditRow(
            plan_id=plan.id,
            actor=plan.actor,
            metric_id=change.after.definition.id,
            from_version=change.before.definition.version,
            to_version=change.after.definition.version,
            event_id=change.event_id,
            action_type=plan.action_type,
        )
    )


def audit_in_session(session: Session, metric_id: str) -> tuple[MetricAudit, ...]:
    """Read transitions in deterministic version order without opening a transaction."""
    return tuple(
        MetricAudit(
            plan_id=row.plan_id,
            actor=row.actor,
            metric_id=row.metric_id,
            from_version=row.from_version,
            to_version=row.to_version,
            event_id=row.event_id,
            action_type=row.action_type,
            created_at=datetime.fromtimestamp(row.created_at, UTC),
        )
        for row in session.scalars(
            select(MetricAuditRow)
            .where(MetricAuditRow.metric_id == metric_id)
            .order_by(MetricAuditRow.to_version)
        )
    )


__all__ = ["MetricAuditRow", "MetricHistory", "audit_in_session", "record_metric_audit"]
