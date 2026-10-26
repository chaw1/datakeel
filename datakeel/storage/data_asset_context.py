# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Filter transient Agent context using current grants while preserving stored history."""

from datakeel.core.agent_models import Conversation
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, NotFoundError
from datakeel.core.memory_models import MemoryEntry
from datakeel.core.models import AssetRef
from datakeel.storage.conversation_asset_refs import conversation_asset_refs, memory_asset_refs
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database

_CALLER = AccessContext(actor="local", entry="agent", scope="query")


def _allowed(db: Database, refs: tuple[AssetRef, ...]) -> bool:
    try:
        require_access(db, refs, _CALLER, record=False)
    except AuthorizationError:
        return False
    return True


def project_agent_history(db: Database, conversation: Conversation) -> Conversation:
    """Drop derived history if a formerly readable resource has lost authorization.

    Root user speech remains original; generated child tasks are derived history.
    Stored transcripts and append-only audit are never rewritten.
    """
    try:
        if _allowed(db, conversation_asset_refs(db, conversation.id)):
            return conversation
    except AuthorizationError:
        pass
    return conversation.model_copy(
        update={
            "messages": [
                item
                for item in conversation.messages
                if item.role == "system"
                or (item.role == "user" and conversation.parent_conversation_id is None)
            ],
            "events": [],
        }
    )


def read_agent_histories(db: Database, conversations: list[Conversation]) -> list[Conversation]:
    """Project currently readable transcripts and audit their combined returned resources once."""
    views = [project_agent_history(db, item) for item in conversations]
    refs = tuple(
        ref
        for original, view in zip(conversations, views, strict=True)
        if original is view
        for ref in conversation_asset_refs(db, original.id)
    )
    require_access(db, refs, _CALLER)
    return views


def require_agent_history(db: Database, conversation_id: str) -> None:
    """Authorize and audit an immutable response replay before returning any cached bytes."""
    require_access(db, conversation_asset_refs(db, conversation_id), _CALLER)


def visible_memories(
    db: Database, entries: list[MemoryEntry], *, record: bool = False
) -> list[MemoryEntry]:
    """Exclude scoped or source-attributed memory whose underlying asset is no longer readable."""
    visible: list[MemoryEntry] = []
    returned_refs: list[AssetRef] = []
    for entry in entries:
        try:
            refs = memory_asset_refs(db, [entry])
        except (AuthorizationError, NotFoundError):
            continue
        if _allowed(db, refs):
            visible.append(entry)
            returned_refs.extend(refs)
    if record:
        require_access(db, tuple(returned_refs), _CALLER)
    return visible
