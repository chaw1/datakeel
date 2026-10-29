# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind production request identities to their original frozen action plans."""

from sqlalchemy import ForeignKey, String, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from datakeel.actions.models import ActionContext, ActionPlan
from datakeel.actions.policy import digest
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.base import Base


class ProductionPreparationRow(Base):
    """Use a database key to bind actor/action/request to exactly one preparation."""

    __tablename__ = "production_preparations"
    actor: Mapped[str] = mapped_column(String, primary_key=True)
    action_type: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    request_digest: Mapped[str] = mapped_column(String)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), unique=True)


def replay_prepared(
    session: Session, action_type: str, params: JsonDocument, context: ActionContext
) -> ActionPlan | None:
    """Return a previous plan only for the same caller parameters and scope limits."""
    request_id = params.root.get("request_id")
    if not isinstance(request_id, str):
        return None
    if session.get_bind().dialect.name == "postgresql":
        key = digest([context.actor, action_type, request_id])
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
    row = session.get(ProductionPreparationRow, (context.actor, action_type, request_id))
    if row is None:
        return None
    if row.request_digest != digest(params.root):
        msg = "Request ID already binds different action parameters"
        raise ConflictError(msg)
    stored = session.scalar(select(ActionPlanRow).where(ActionPlanRow.id == row.plan_id))
    if stored is None:
        msg = "Request's original plan is missing"
        raise NotFoundError(msg)
    plan = ActionPlan.model_validate(stored.payload).model_copy(update={"status": stored.status})
    if plan.context != context:
        msg = "Request ID already binds different caller limits"
        raise ConflictError(msg)
    return plan


def remember_prepared(session: Session, plan: ActionPlan, params: JsonDocument) -> None:
    """Persist the request binding in the same transaction as the first preparation."""
    request_id = params.root.get("request_id")
    if isinstance(request_id, str):
        session.add(
            ProductionPreparationRow(
                actor=plan.actor,
                action_type=plan.action_type,
                request_id=request_id,
                request_digest=digest(params.root),
                plan_id=plan.id,
            )
        )
