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
# Match existing worker order: append observations before publishing versions.
PREDICATE_TABLES = ("datasets", "lineage_events", "versions", "file_states")
TABLE_WIDE_MODE = "SHARE ROW EXCLUSIVE"


def table_locks(action_type: str | None) -> tuple[tuple[str, ...], str]:
    """Return the tables and mode an action locks on PostgreSQL before touching any row.

    Every action takes its table-level locks first and its row locks afterwards, so no two
    actions can wait for each other in opposite orders. Table-wide actions hold SHARE ROW
    EXCLUSIVE on the predicate tables. Among those tables a single-task action writes only its
    lineage receipt, so it takes that table's ROW EXCLUSIVE lock up front instead of at insert
    time: the mode conflicts with the table-wide lock but not with itself, which keeps
    annotators concurrent while a table-wide action never waits for a task row that a receipt
    writer holds.
    """
    if action_type in ROW_SCOPED_ACTIONS:
        return ("lineage_events",), "ROW EXCLUSIVE"
    return PREDICATE_TABLES, TABLE_WIDE_MODE


def lock_action_targets(db: Database, session: Session, plan_id: str | None = None) -> None:
    """Serialize fact changes that could alter an approved predicate or export."""
    db.lock_writes(session)
    if db.sqlite:
        return
    action_type = (
        session.scalar(select(ActionPlanRow.action_type).where(ActionPlanRow.id == plan_id))
        if plan_id is not None
        else None
    )
    tables, mode = table_locks(action_type)
    if tables:
        session.execute(text(f"LOCK TABLE {', '.join(tables)} IN {mode} MODE"))


def lock_row_writes(db: Database, session: Session) -> None:
    """Lock like a single-task action: work a long run writes in short per-batch transactions.

    Taking the receipt table's ROW EXCLUSIVE lock before any task row keeps the same order as
    every other action, so a batch never deadlocks with a table-wide action.
    """
    db.lock_writes(session)
    if db.sqlite:
        return
    tables, mode = table_locks("save_revision")
    session.execute(text(f"LOCK TABLE {', '.join(tables)} IN {mode} MODE"))
