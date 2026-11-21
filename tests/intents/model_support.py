# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic planner attempts with real routing and persistence boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import send_message
from datakeel.core.agent_models import MessageInput, ModelRequest, ModelResponse, ScriptedResponse
from datakeel.intents.model_parse import AGENT_NAME

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from datakeel.agent.models import AgentEvent
    from datakeel.core.errors import ProviderError
    from datakeel.core.intent_models import PageContext
    from datakeel.storage.database import Database

REQUEST = "Create a vehicle label set with car and truck"
PLAN = (
    '{"kind":"plan","steps":[{"id":"s1","action":"create_label_set",'
    '"params":{"name":"Vehicles","labels":[{"id":"car","name":"car"},'
    '{"id":"truck","name":"truck"}]}}]}'
)


class PlannerProvider(FakeProvider):
    """Fail selected invocations while keeping successful scripted replies queued."""

    def __init__(
        self,
        replies: Sequence[str | ModelResponse] = (PLAN,),
        failures: dict[int, ProviderError] | None = None,
        on_attempt: Callable[[int], None] | None = None,
    ) -> None:
        """Mark responses as planner replies so legacy fake-provider opt-in stays intact."""
        super().__init__(
            [
                ScriptedResponse(agent=AGENT_NAME, content=reply)
                if isinstance(reply, str)
                else ScriptedResponse.model_validate({**reply.model_dump(), "agent": AGENT_NAME})
                for reply in replies
            ]
        )
        self.failures = failures or {}
        self.on_attempt = on_attempt

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Capture the same provider request that routing reserves and settles."""
        attempt = len(self.requests) + 1
        if self.on_attempt is not None:
            self.on_attempt(attempt)
        if error := self.failures.get(attempt):
            self.requests.append(request)
            raise error
        return super().complete(request)


def send_planner(
    db: Database,
    conversation_id: str,
    provider: PlannerProvider,
    text: str = REQUEST,
    context: PageContext | None = None,
) -> list[AgentEvent]:
    """Exercise the public response stream, including its final model route decisions."""
    return list(
        send_message(
            db,
            conversation_id,
            MessageInput(content=text, context=context),
            provider=provider,
        )
    )
