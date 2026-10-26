# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authorize source data disclosed by controlled plans and their durable receipts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.data_asset_models import AccessContext
from datakeel.storage.action_store import locked_plan
from datakeel.storage.data_asset_access import require_access_in_session

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datakeel.actions.models import ActionPlan, ActionRun
    from datakeel.core.models import AssetRef
    from datakeel.storage.database import Database


def authorize_plans_in_session(
    session: Session,
    plans: tuple[ActionPlan, ...],
    access: AccessContext | None = None,
    *,
    actor: str | None = None,
    record: bool = True,
) -> None:
    """Check frozen source manifests without locking public asset-card administration.

    Export plans disclose their source under export scope. Other source-bearing
    plans use query scope. Empty manifests contain explicit administrative metadata.
    Group a collection by caller and scope so one response audits each asset once.
    """
    groups: dict[str, tuple[AccessContext, list[AssetRef]]] = {}
    for plan in plans:
        if not plan.manifest.objects:
            continue
        scope = "export" if plan.action_type == "export_dataset" else "query"
        caller = access or AccessContext(
            actor=actor if actor is not None else "local",
            entry="export" if scope == "export" else "ask",
            scope=scope,
        )
        caller = AccessContext(
            actor=actor if actor is not None else caller.actor, entry=caller.entry, scope=scope
        )
        _, refs = groups.setdefault(caller.model_dump_json(), (caller, []))
        refs.extend(item.asset_ref for item in plan.manifest.objects)
    for caller, refs in groups.values():
        require_access_in_session(session, tuple(refs), caller, record=record)


def authorize_plan(db: Database, plan: ActionPlan, access: AccessContext | None = None) -> None:
    """Recheck a previously returned plan before replaying its source-bearing contents."""
    with db.session() as session:
        db.lock_writes(session)
        authorize_plans_in_session(session, (plan,), access)
        session.commit()


def authorize_run(db: Database, run: ActionRun, access: AccessContext | None = None) -> None:
    """Bind receipt disclosure to the original plan's current source authorization."""
    with db.session() as session:
        db.lock_writes(session)
        plan = locked_plan(session, run.plan_id)[1]
        authorize_plans_in_session(session, (plan,), access)
        session.commit()
