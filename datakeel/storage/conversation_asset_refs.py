# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve derived conversation content through tool, delegation and memory provenance."""

from collections.abc import Iterable

from sqlalchemy import select

from datakeel.core.agent_models import Conversation
from datakeel.core.errors import AuthorizationError
from datakeel.core.memory_models import MemoryEntry
from datakeel.core.models import AssetRef
from datakeel.storage.conversation_store import get, list_all
from datakeel.storage.database import Database
from datakeel.storage.memory_rows import MemoryRow, MemoryUseRow
from datakeel.storage.tool_invocations import list_invocations


class _Sources:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.conversations = {item.id: item for item in list_all(db, include_children=True)}
        with db.session() as session:
            self.memories = {
                row.id: MemoryEntry.model_validate(row.payload)
                for row in session.scalars(select(MemoryRow))
            }
            self.memory_uses: dict[str, set[str]] = {}
            for row in session.scalars(select(MemoryUseRow)):
                self.memory_uses.setdefault(row.root_conversation_id, set()).add(row.memory_id)
        self.seen_conversations: set[str] = set()
        self.seen_memories: set[str] = set()
        self.pending_conversations: list[str] = []
        self.pending_memories: list[MemoryEntry] = []
        self.refs: dict[tuple[str, str, str, str | None], AssetRef] = {}

    def _add(self, refs: Iterable[AssetRef]) -> None:
        for ref in refs:
            self.refs[ref.namespace, ref.asset_type, ref.asset_id, ref.version] = ref

    def _entry(self, identifier: str) -> MemoryEntry:
        entry = self.memories.get(identifier)
        if entry is None:
            msg = "Memory source history is unavailable; apply for access"
            raise AuthorizationError(msg)
        return entry

    def _conversation(self, identifier: str) -> None:
        if identifier in self.seen_conversations:
            return
        self.seen_conversations.add(identifier)
        conversation = self.conversations.get(identifier)
        if conversation is None:
            msg = "Conversation source history is unavailable; apply for access"
            raise AuthorizationError(msg)
        if conversation.parent_conversation_id:
            self.pending_conversations.append(conversation.parent_conversation_id)
        self.pending_conversations.extend(
            item.id
            for item in self.conversations.values()
            if item.parent_conversation_id == identifier
        )
        self._add(
            ref
            for invocation in list_invocations(self.db, identifier)
            if invocation.status == "SUCCEEDED"
            for ref in invocation.asset_refs
        )
        snapshots = self._snapshots(conversation)
        self._add(ref for refs in snapshots.values() for ref in refs)
        identifiers = set(self.memory_uses.get(conversation.root_conversation_id or identifier, ()))
        for event in conversation.events:
            used = event.root.get("used_memory_ids", [])
            if not isinstance(used, list) or any(not isinstance(key, str) for key in used):
                msg = "Memory source history is invalid; apply for access"
                raise AuthorizationError(msg)
            identifiers.update(key for key in used if isinstance(key, str))
        self.pending_memories.extend(
            self._entry(key) for key in identifiers if key not in snapshots
        )

    def _snapshots(self, conversation: Conversation) -> dict[str, list[AssetRef]]:
        root_id = conversation.root_conversation_id or conversation.id
        snapshots: dict[str, list[AssetRef]] = {}
        for item in self.conversations.values():
            if (item.root_conversation_id or item.id) == root_id:
                for source in item.memory_sources:
                    snapshots.setdefault(source.memory_id, []).extend(source.asset_refs)
        return snapshots

    def _memory(self, entry: MemoryEntry) -> None:
        if entry.id in self.seen_memories:
            return
        self.seen_memories.add(entry.id)
        if entry.dataset_id:
            self._add((AssetRef(asset_id=entry.dataset_id),))
        self.pending_conversations.extend(entry.source_conversation_ids)
        self.pending_memories.extend(self._entry(key) for key in entry.source_memory_ids)

    def resolve(self) -> tuple[AssetRef, ...]:
        while self.pending_conversations or self.pending_memories:
            if self.pending_conversations:
                self._conversation(self.pending_conversations.pop())
            else:
                self._memory(self.pending_memories.pop())
        return tuple(self.refs[key] for key in sorted(self.refs, key=str))


def conversation_asset_refs(db: Database, conversation_id: str) -> tuple[AssetRef, ...]:
    """Collect resource attribution across child sessions, including legacy memory consumers."""
    get(db, conversation_id)
    sources = _Sources(db)
    sources.pending_conversations.append(conversation_id)
    return sources.resolve()


def memory_asset_refs(db: Database, entries: list[MemoryEntry]) -> tuple[AssetRef, ...]:
    """Resolve source-attributed entries without returning or retaining their text."""
    sources = _Sources(db)
    sources.pending_memories.extend(entries)
    return sources.resolve()
