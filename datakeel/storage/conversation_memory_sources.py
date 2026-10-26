# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist content-free memory provenance before the consuming provider attempt."""

from datakeel.core.agent_models import Conversation, MemorySourceSnapshot
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ConflictError
from datakeel.core.memory_models import MemoryEntry
from datakeel.storage.conversation_asset_refs import memory_asset_refs
from datakeel.storage.conversation_store import locked_conversation
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database


def remember_memory_sources(
    db: Database, conversation_id: str, token: str, entries: list[MemoryEntry]
) -> None:
    """Freeze resource references under the active response lease, never memory content."""
    if not entries:
        return
    sources = [
        MemorySourceSnapshot(
            memory_id=entry.id,
            asset_refs=tuple(
                ref.model_copy(update={"display_name": None})
                for ref in memory_asset_refs(db, [entry])
            ),
        )
        for entry in entries
    ]
    require_access(
        db,
        tuple(ref for source in sources for ref in source.asset_refs),
        AccessContext(actor="local", entry="agent", scope="query"),
        record=False,
    )
    with db.session() as session:
        db.lock_writes(session)
        row = locked_conversation(session, conversation_id)
        if row.active_token != token:
            msg = "Conversation response lease was lost"
            raise ConflictError(msg)
        conversation = Conversation.model_validate(row.payload)
        known = {item.memory_id: item for item in conversation.memory_sources}
        for source in sources:
            previous = known.get(source.memory_id)
            refs = (
                tuple(dict.fromkeys((*previous.asset_refs, *source.asset_refs)))
                if previous
                else source.asset_refs
            )
            known[source.memory_id] = source.model_copy(update={"asset_refs": refs})
        row.payload = conversation.model_copy(
            update={"memory_sources": tuple(known[key] for key in sorted(known))}
        ).model_dump(mode="json")
        session.commit()
