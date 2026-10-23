# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic provider scripts retained independently of the model runtime."""

import json
from collections.abc import Sequence

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.harness_models import TokenUsage
from datakeel.delegation.scripts import prepare_script


class FakeProvider:
    """Replay an explicit script while retaining every request for assertions."""

    def __init__(self, script: Sequence[ModelResponse]) -> None:
        """Copy the scripted response queue so fixtures cannot mutate it accidentally."""
        self.script = list(script)
        self.requests: list[ModelRequest] = []
        self.script_errors: list[str] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Return the next script entry, deriving fixture usage when omitted."""
        self.requests.append(request)
        result = self.script.pop(0) if self.script else ModelResponse(content="Complete.")
        result = prepare_script(request, result, self.script_errors)
        if result.usage.input_tokens:
            return result
        usage = TokenUsage(
            input_tokens=sum(segment.tokens for segment in request.segments),
            output_tokens=max(1, len(json.dumps(result.model_dump(mode="json"))) // 4),
        )
        return result.model_copy(update={"usage": usage})
