# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real MCP sessions can reopen explicit Ask threads without model calls."""

import asyncio
from pathlib import Path

from fastmcp import Client

from datakeel.core.ask_models import AskAnswer
from datakeel.core.models import JsonDocument
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.database import Database
from tests.enterprise_support import enterprise_fixture


def test_mcp_accepts_question_thread_and_matches_equivalent_full_query(
    db: Database, tmp_path: Path
) -> None:
    """Protocol schemas, dispatch and structured results preserve chart and follow-up data."""
    enterprise_fixture(db, tmp_path / "enterprise")

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            tool = next(item for item in await client.list_tools() if item.name == "ask_data")
            assert "conversation_id" in tool.input_schema["properties"]
            answers: list[AskAnswer] = []
            for question in (
                "上个季度华东区零售额是多少",
                "那华南呢",
                "上个季度华南区零售额是多少",
            ):
                arguments = JsonDocument(
                    {
                        "question": question,
                        "reference_instant": "2026-10-01T00:00:00Z",
                        "conversation_id": answers[0].conversation_id
                        if len(answers) == 1
                        else None,
                    }
                )
                result = await client.call_tool("ask_data", arguments.root)
                outcome = ToolOutcome.model_validate(result.structured_content)
                assert outcome.status == "SUCCEEDED", outcome.error
                answers.append(AskAnswer.model_validate(outcome.content.root["data"]))
            assert answers[0].conversation_id == answers[1].conversation_id
            assert answers[1].result == answers[2].result
            assert answers[1].interpreted_question
            assert answers[1].chart is not None

    asyncio.run(scenario())
