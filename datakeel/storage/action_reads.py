# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public controlled-action views revalidate every disclosed source under current grants."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.storage import action_store
from datakeel.storage.action_access import authorize_plans_in_session
from datakeel.storage.database import Database


def get_plan(db: Database, plan_id: str, *, access: AccessContext | None = None) -> ActionPlan:
    """Read a current plan only while its manifest remains authorized for this caller."""
    with db.session() as session:
        db.lock_writes(session)
        plan = action_store.locked_plan(session, plan_id)[1]
        authorize_plans_in_session(session, (plan,), access)
        session.commit()
        return plan


def list_approvals(db: Database, *, access: AccessContext | None = None) -> list[ActionPlan]:
    """Read pending plans without leaking an unauthorized frozen manifest in a collection."""
    plans = action_store.list_approvals(db)
    with db.session() as session:
        db.lock_writes(session)
        visible = _visible_plans(session, tuple(plans), access)
        authorize_plans_in_session(session, visible, access)
        session.commit()
    return list(visible)


def list_runs(db: Database, *, access: AccessContext | None = None) -> list[ActionRun]:
    """Read receipt history, including prior metadata values, under current source grants."""
    runs = action_store.list_runs(db)
    with db.session() as session:
        db.lock_writes(session)
        plans = tuple(
            action_store.locked_plan(session, identifier)[1]
            for identifier in sorted({run.plan_id for run in runs})
        )
        visible = _visible_plans(session, plans, access)
        authorize_plans_in_session(session, visible, access)
        allowed = {plan.id for plan in visible}
        session.commit()
    return [run for run in runs if run.plan_id in allowed]


def _visible_plans(
    session: Session, plans: tuple[ActionPlan, ...], access: AccessContext | None
) -> tuple[ActionPlan, ...]:
    visible: list[ActionPlan] = []
    for plan in plans:
        try:
            authorize_plans_in_session(session, (plan,), access, record=False)
        except AuthorizationError:
            continue
        visible.append(plan)
    return tuple(visible)
