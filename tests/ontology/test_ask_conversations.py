# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Agent reads discover the same question-thread contract without runtime coupling."""

from pathlib import Path

from datakeel.agent.tools import deferred_tools
from datakeel.core.ask_models import AskAnswer
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.ask_conversations import delete_conversation, get_conversation
from datakeel.storage.database import Database
from tests.enterprise_support import enterprise_fixture


def test_agent_read_tool_continues_explicit_ask_thread_across_tool_sessions(
    db: Database, tmp_path: Path
) -> None:
    """Only conversation_id controls Ask context; an Agent session ID grants no ownership."""
    enterprise_fixture(db, tmp_path / "enterprise")
    definition = next(item for item in deferred_tools() if item.name == "ask_data")
    properties = definition.parameters.root["properties"]
    assert isinstance(properties, dict)
    assert "conversation_id" in properties
    first = invoke_tool(
        db,
        "ask_data",
        JsonDocument(
            {"question": "上个季度华东区零售额是多少", "reference_instant": "2026-10-01T00:00:00Z"}
        ),
        ToolCallContext(agent_id="generated-agent", session_id="agent-session-one"),
    )
    assert first.status == "SUCCEEDED"
    answer = AskAnswer.model_validate(first.content.root["data"])
    follow = invoke_tool(
        db,
        "ask_data",
        JsonDocument(
            {
                "question": "那华南呢",
                "reference_instant": "2026-10-01T00:00:00Z",
                "conversation_id": answer.conversation_id,
            }
        ),
        ToolCallContext(agent_id="generated-agent", session_id="agent-session-two"),
    )
    assert follow.status == "SUCCEEDED"
    followed = AskAnswer.model_validate(follow.content.root["data"])
    assert followed.status == "answered"
    assert followed.conversation_id == answer.conversation_id
    assert followed.chart is not None
    assert followed.interpreted_question
    assert answer.conversation_id is not None
    thread = get_conversation(db, answer.conversation_id, actor="local")
    assert [turn.id for turn in thread.turns] == [answer.id, followed.id]


def test_deleted_question_thread_cannot_replay_cached_agent_tool_answer(
    db: Database, tmp_path: Path
) -> None:
    """Deleting answer rows also closes the durable tool-call replay path to that answer."""
    enterprise_fixture(db, tmp_path / "enterprise")
    arguments = JsonDocument(
        {"question": "上个季度华东区零售额是多少", "reference_instant": "2026-10-01T00:00:00Z"}
    )
    context = ToolCallContext(agent_id="generated-agent", session_id="generated-agent-session")
    first = invoke_tool(db, "ask_data", arguments, context, call_id="generated-call")
    assert first.status == "SUCCEEDED"
    answer = AskAnswer.model_validate(first.content.root["data"])
    assert answer.result is not None
    assert answer.conversation_id is not None
    assert invoke_tool(db, "ask_data", arguments, context, call_id="generated-call") == first
    delete_conversation(db, answer.conversation_id, actor="local")
    replayed = invoke_tool(db, "ask_data", arguments, context, call_id="generated-call")
    assert replayed.status == "FAILED"
    assert replayed.content.root == {}
    assert replayed.error
