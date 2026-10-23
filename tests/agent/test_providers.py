# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Provider wire protocols remain deterministic without accessing external services."""

from __future__ import annotations

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.core.agent_models import (
    ChatMessage,
    ContextSegment,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolDefinition,
)
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument


@pytest.fixture
def model_request() -> ModelRequest:
    """Represent a complete prior call/result pair plus stable system guidance."""
    call = ToolCall(id="call-1", name="search_files", arguments=JsonDocument({"quality_max": 60}))
    return ModelRequest(
        model="fixture-model",
        messages=[
            ChatMessage(role="system", content="Use controlled tools."),
            ChatMessage(role="user", content="Find low quality files."),
            ChatMessage(role="assistant", content="Searching.", tool_calls=[call]),
            ChatMessage(role="tool", content='{"matches": []}', tool_call_id=call.id),
        ],
        tools=[
            ToolDefinition(
                name="search_files",
                description="Find selected files.",
                parameters=JsonDocument({"type": "object"}),
            )
        ],
        segments=[ContextSegment(name="system", kind="stable", text="guidance", tokens=10)],
        max_output_tokens=100,
    )


def test_fake_when_script_consumed_retains_requests_and_derives_fixture_tokens(
    model_request: ModelRequest,
) -> None:
    """Allow deterministic replay with explicit or derived provider usage."""
    specified = ModelResponse(content="Measured", usage=TokenUsage(input_tokens=5, output_tokens=2))
    provider = FakeProvider([specified, ModelResponse(content="Derived")])
    assert provider.complete(model_request) == specified
    assert provider.complete(model_request).usage.input_tokens == 10
    assert provider.complete(model_request).content == "Complete."
    assert provider.requests == [model_request] * 3
