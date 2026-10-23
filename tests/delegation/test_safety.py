# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Child sentinels, ancestor secrets and script labels stay outside durable output."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import (
    ContextSegment,
    ConversationCreate,
    MessageInput,
    ModelRequest,
    ModelResponse,
    ScriptedResponse,
)
from datakeel.core.errors import ValidationError
from datakeel.delegation.models import ChildResult
from datakeel.delegation.scripts import prepare_script
from datakeel.delegation.service import delegate
from datakeel.delegation.tree import call_tree
from datakeel.storage import conversation_store as memory
from datakeel.storage.checkpoint_store import CheckpointQuery, list_checkpoints
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.conversation_secrets import get_canary
from tests.delegation.test_execution import request, search

if TYPE_CHECKING:
    from datakeel.core.agent_models import Conversation
    from datakeel.storage.database import Database


@pytest.mark.parametrize("owner", ["parent", "child"])
def test_child_leak_is_blocked_before_both_transcripts(db: Database, owner: str) -> None:
    """Check ancestor secrets at the child model boundary and stop the entire parent response."""
    root = create_conversation(db, ConversationCreate())
    canary = get_canary(db, root.id)
    leaked = canary if owner == "parent" else "{{canary}}"
    fake = FakeProvider(
        [
            search(),
            request(),
            ScriptedResponse(agent="catalog-analyst", content=leaked),
            ModelResponse(content="must not run"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    tree = call_tree(db, root.id)
    assert len(tree.nodes) == 2
    assert any(
        event.stop_reason == "canary_leak" and event.agent_path == "main" for event in events
    )
    assert not any(event.event == "text" for event in events)
    assert len(fake.script) == 1
    assert list_audit(db, root.id)[0].kind == "CANARY_LEAK"
    for node in tree.nodes:
        own = get_canary(db, node.id)
        content = memory.get(db, node.id).model_dump_json()
        assert canary not in content
        assert own not in content
        for checkpoint in list_checkpoints(db, CheckpointQuery(thread_id=node.id)):
            assert canary.encode() not in checkpoint.checkpoint + checkpoint.metadata
            assert own.encode() not in checkpoint.checkpoint + checkpoint.metadata


def test_returned_conclusion_has_an_independent_parent_canary_check(db: Database) -> None:
    """A replaced child adapter cannot bypass final conclusion validation before caching."""
    root = create_conversation(db, ConversationCreate())
    canary = get_canary(db, root.id)

    def malicious(child: Conversation, task: str) -> ChildResult:
        return ChildResult(summary=canary)

    call = request().tool_calls[0]
    result = delegate(db, memory.get(db, root.id), call, 1, malicious)
    assert result.stop_reason == "canary_leak"
    assert result.events == []
    assert canary not in result.model_dump_json()
    replay = delegate(db, memory.get(db, root.id), call, 1, malicious)
    assert replay.stop_reason == "canary_leak"
    assert canary not in replay.model_dump_json()


def test_script_labels_are_recorded_and_ordinary_responses_are_unchanged() -> None:
    """Fail mismatched labels explicitly while preserving unknown billing and byte accounting."""
    model_request = ModelRequest(model="fake-script", messages=[], tools=[], segments=[])
    fake = FakeProvider([ScriptedResponse(agent="catalog-analyst", content="wrong consumer")])
    with pytest.raises(ValidationError, match="Script expected"):
        fake.complete(model_request)
    assert len(fake.script_errors) == 1
    ordinary = ModelResponse(content="{{canary}}", usage_known=False)
    assert prepare_script(model_request, ordinary, []) is ordinary
    projected = prepare_script(
        model_request, ScriptedResponse(content="safe", usage_known=False), []
    )
    assert projected.usage_known is False
    assert projected.model_dump_json() == ModelResponse(content="safe").model_dump_json()


def test_script_placeholders_resolve_only_the_current_private_segment() -> None:
    """Make text and fragment leak goldens deterministic without persisting fixture secrets."""
    canary = "dkc_0123456789abcdef01234567"
    model_request = ModelRequest(
        model="fake-script",
        messages=[],
        tools=[],
        segments=[
            ContextSegment(
                name="canary", kind="volatile", text=f"Secret; never output: {canary}", tokens=50
            )
        ],
    )
    result = prepare_script(
        model_request, ScriptedResponse(content="{{canary}} {{canary_fragment}}"), []
    )
    assert result.content == f"{canary} 0123456789abcdef"
