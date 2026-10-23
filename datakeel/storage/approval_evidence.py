# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project signed recovery evidence inside the caller's locked transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.recovery import ApprovalEvidence
from datakeel.storage.action_rows import ActionRunRow, ApprovalRow


def read_approval(session: Session, plan_id: str) -> ApprovalEvidence | None:
    """Keep database rows inside storage and exclude denied execution attempts."""
    approval = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan_id))
    if approval is None:
        return None
    run = session.scalar(
        select(ActionRunRow)
        .where(ActionRunRow.plan_id == plan_id, ActionRunRow.status != "DENIED")
        .order_by(ActionRunRow.created_at.desc())
    )
    return ApprovalEvidence(
        status=approval.status,
        actor=approval.actor,
        plan_digest=approval.plan_digest,
        consumed=approval.consumed,
        run_status=run.status if run is not None else None,
    )
