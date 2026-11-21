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
from datakeel.storage.identity_sessions import session_actor, session_actors


def _require_agent_access(
    db: Database, refs: tuple[AssetRef, ...], actor: str, *, record: bool = False
) -> None:
    require_access(
        db, refs, AccessContext(actor=actor, entry="agent", scope="query"), record=record
    )


def project_agent_history(
    db: Database, conversation: Conversation, *, actor: str | None = None
) -> Conversation:
    """Drop derived history if a formerly readable resource has lost authorization.

    Root user speech remains original; generated child tasks are derived history.
    Stored transcripts and append-only audit are never rewritten.
    """
    try:
        refs = conversation_asset_refs(db, conversation.id)
        actor = actor if actor is not None else session_actor(db, conversation.id)
        _require_agent_access(db, refs, actor)
    except AuthorizationError:
        roles = {"system", "user"} if conversation.parent_conversation_id is None else {"system"}
        return conversation.model_copy(
            update={
                "messages": [item for item in conversation.messages if item.role in roles],
                "events": [],
            }
        )
    return conversation


def read_agent_histories(db: Database, conversations: list[Conversation]) -> list[Conversation]:
    """Project currently readable transcripts and audit their combined returned resources once."""
    actors = session_actors(db, [item.id for item in conversations])
    views = [project_agent_history(db, item, actor=actors[item.id]) for item in conversations]
    groups: dict[str, list[AssetRef]] = {}
    for original, view in zip(conversations, views, strict=True):
        if original is view:
            actor = actors[original.id]
            groups.setdefault(actor, []).extend(conversation_asset_refs(db, original.id))
    for actor, refs in groups.items():
        _require_agent_access(db, tuple(refs), actor, record=True)
    return views


def require_agent_history(db: Database, conversation_id: str) -> None:
    """Authorize and audit an immutable response replay before returning any cached bytes."""
    refs = conversation_asset_refs(db, conversation_id)
    _require_agent_access(db, refs, session_actor(db, conversation_id), record=True)


def visible_memories(
    db: Database, entries: list[MemoryEntry], *, record: bool = False, actor: str = "local"
) -> list[MemoryEntry]:
    """Exclude scoped or source-attributed memory whose underlying asset is no longer readable."""
    visible: list[MemoryEntry] = []
    returned_refs: list[AssetRef] = []
    for entry in entries:
        try:
            refs = memory_asset_refs(db, [entry])
        except (AuthorizationError, NotFoundError):
            continue
        try:
            _require_agent_access(db, refs, actor)
        except AuthorizationError:
            continue
        visible.append(entry)
        returned_refs.extend(refs)
    if record:
        _require_agent_access(db, tuple(returned_refs), actor, record=True)
    return visible
