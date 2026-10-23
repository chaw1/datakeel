# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Consistent predicate locking for frozen action executions and receipts."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from datakeel.storage.database import Database


def lock_action_targets(db: Database, session: Session) -> None:
    """Serialize fact changes that could alter an approved predicate or export."""
    db.lock_writes(session)
    if not db.sqlite:
        # Match existing worker order: append observations before publishing versions.
        session.execute(
            text(
                "LOCK TABLE datasets, lineage_events, versions, file_states "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
