# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Consistent predicate locking for frozen action executions and receipts."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.database import Database

# Per-task production work reads and writes only its own task, assignment, revision, review and
# counter rows. Each business function locks the task row first and counters change through
# atomic updates at commit, so these actions skip the table-wide predicate lock that guards
# datasets, versions and exports. Approved tasks only change again through reopen, which keeps
# that lock. This is what lets dozens of annotators claim and save concurrently.
ROW_SCOPED_ACTIONS = frozenset(
    {"claim_task", "release_task", "heartbeat", "save_revision", "submit_task", "review_task"}
)


def lock_action_targets(db: Database, session: Session, plan_id: str | None = None) -> None:
    """Serialize fact changes that could alter an approved predicate or export."""
    db.lock_writes(session)
    if db.sqlite:
        return
    if plan_id is not None:
        action_type = session.scalar(
            select(ActionPlanRow.action_type).where(ActionPlanRow.id == plan_id)
        )
        if action_type in ROW_SCOPED_ACTIONS:
            return
    # Match existing worker order: append observations before publishing versions.
    session.execute(
        text(
            "LOCK TABLE datasets, lineage_events, versions, file_states IN SHARE ROW EXCLUSIVE MODE"
        )
    )
