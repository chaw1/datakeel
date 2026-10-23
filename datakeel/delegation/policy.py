# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enforce depth, batch size and transitive specialist capability restrictions."""

from datakeel.core.agent_models import Conversation, ModelResponse
from datakeel.core.canary import response_leaks
from datakeel.core.settings import get_settings
from datakeel.delegation.models import AgentDefinition
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.conversation_store import get
from datakeel.storage.database import Database


def rejection(parent: Conversation, definition: AgentDefinition, ordinal: int) -> str:
    """Count requested siblings in one reply while execution remains strictly serial."""
    limits = get_settings()
    if parent.depth >= limits.delegation_max_depth:
        return "delegation_depth_exceeded"
    if ordinal > limits.delegation_max_parallel:
        return "delegation_parallel_exceeded"
    if parent.allowed_tools is not None and not set(definition.tools).issubset(
        parent.allowed_tools
    ):
        return "delegation_scope_exceeded"
    return ""


def tool_allowed(scope: list[str] | None, name: str) -> bool:
    """Apply the same explicit scope during discovery, restore and dispatch."""
    return scope is None or name in scope or name == "tool_search"


def ancestor_leak(db: Database, conversation: Conversation, response: ModelResponse) -> bool:
    """Check ancestor secrets before a child's reply can enter its own transcript."""
    parent_id = conversation.parent_conversation_id
    while parent_id is not None:
        if response_leaks(get_canary(db, parent_id), response):
            return True
        parent_id = get(db, parent_id).parent_conversation_id
    return False
