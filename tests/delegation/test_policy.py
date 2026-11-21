# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Streaming policy includes every ancestor without exposing unrelated secrets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.agent_models import Conversation, ConversationCreate
from datakeel.core.models import new_id
from datakeel.delegation.policy import conversation_canaries
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_secrets import get_canary

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_canaries_follow_current_parent_and_root_order(db: Database) -> None:
    """Read the persisted family rather than siblings or only the immediate parent."""
    root = memory.create(db, ConversationCreate())
    parent = memory.store(
        db, Conversation(id=new_id(), config=root.config, parent_conversation_id=root.id)
    )
    child = memory.store(
        db, Conversation(id=new_id(), config=root.config, parent_conversation_id=parent.id)
    )
    memory.create(db, ConversationCreate())
    assert conversation_canaries(db, root) == (get_canary(db, root.id),)
    assert conversation_canaries(db, child) == tuple(
        get_canary(db, conversation.id) for conversation in (child, parent, root)
    )
