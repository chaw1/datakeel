# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public SSE events remain immutable and reject undeclared transport fields."""

import pytest
from pydantic import ValidationError

from datakeel.agent.models import AgentEvent


def test_event_when_serialized_preserves_id_and_typed_stop_reason() -> None:
    """Allow reconnect recovery to retain the original event identity."""
    event = AgentEvent(event="stopped", stop_reason="budget_exceeded")
    assert AgentEvent.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AgentEvent.model_validate({"event": "done", "unknown": True})
