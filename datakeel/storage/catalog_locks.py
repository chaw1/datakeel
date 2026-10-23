# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One catalog lock order shared by publication, semantic changes, and reconstruction."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_catalog(session: Session) -> None:
    """Fence catalog reads and writes in the controlled-action lineage lock order.

    SQLite callers already hold BEGIN IMMEDIATE through Database.lock_writes;
    acquiring another transaction here would invalidate the caller's transaction.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("LOCK TABLE lineage_events IN SHARE ROW EXCLUSIVE MODE"))
