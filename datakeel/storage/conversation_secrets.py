# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep conversation sentinels separate from transcript and public view payloads."""

from datakeel.core.canary import generate_canary
from datakeel.storage.conversation_store import locked_conversation
from datakeel.storage.database import Database


def get_canary(db: Database, conversation_id: str) -> str:
    """Read a sentinel, assigning one transactionally to a migrated legacy conversation."""
    with db.session() as session:
        db.lock_writes(session)
        row = locked_conversation(session, conversation_id)
        if row.canary is None:
            row.canary = generate_canary()
            session.commit()
        return row.canary
