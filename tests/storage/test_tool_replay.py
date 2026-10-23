# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tool correlation IDs retain outcomes across node replays without repeating dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import Conversation, ConversationCreate, ToolCall
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolCallContext, ToolInvocationStart
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.tool_invocations import (
    begin_invocation,
    invocation_identity,
    list_invocations,
    replay_invocation,
)

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_tool_when_correlation_replayed_reuses_original_outcome_and_audit(db: Database) -> None:
    """Persist one invocation for the same call and reject changing its bound request."""
    context = ToolCallContext(session_id="conversation")
    first = invoke_tool(db, "list_datasets", JsonDocument({}), context, call_id="call")
    assert invoke_tool(db, "list_datasets", JsonDocument({}), context, call_id="call") == first
    assert len(list_invocations(db)) == 1
    with pytest.raises(ConflictError, match="different arguments"):
        invoke_tool(db, "list_datasets", JsonDocument({"limit": 2}), context, call_id="call")


def test_tool_when_started_without_outcome_refuses_ambiguous_redispatch(db: Database) -> None:
    """A recorded in-flight call cannot be silently run twice after interruption."""
    request = ToolInvocationStart(
        name="list_datasets",
        arguments_digest="digest",
        argument_keys=[],
        context=ToolCallContext(session_id="session"),
        asset_refs=[],
        identifier=invocation_identity("session", "call"),
    )
    identifier = begin_invocation(db, request)
    with pytest.raises(ConflictError, match="interrupted"):
        replay_invocation(db, identifier, request.name, request.arguments_digest)
    with pytest.raises(ConflictError, match="already has"):
        begin_invocation(db, request)
    assert len(list_invocations(db)) == 1


def test_tool_search_when_replayed_rehydrates_catalog_without_another_span(db: Database) -> None:
    """A replayed discovery restores allowed capabilities and keeps the original invocation."""
    conversation = Conversation(id="session", config=ConversationCreate())
    call = ToolCall(
        id="search", name="tool_search", arguments=JsonDocument({"query": "delete_files"})
    )
    context = ToolCallContext(session_id=conversation.id)
    first = ToolCatalog(conversation).invoke(db, call, context)
    restored = ToolCatalog(conversation)
    assert restored.invoke(db, call, context) == first
    assert "delete_files" in restored.loaded
    assert len(list_invocations(db)) == 1
