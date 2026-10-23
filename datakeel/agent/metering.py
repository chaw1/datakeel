# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve provider-neutral budget and trace accounting around one model attempt."""

from collections.abc import Callable
from time import perf_counter
from typing import Literal

from datakeel.agent.context import allocate_tokens, assemble
from datakeel.agent.demo import DemoProvider
from datakeel.agent.memory import workspace
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ModelRequest, ModelResponse, Provider
from datakeel.core.errors import BudgetError
from datakeel.core.harness_models import BudgetRequest, TraceInput
from datakeel.harness.service import reserve, settle
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database


class ModelMeter:
    """Meter one response without owning its execution scheduler."""

    def __init__(self, db: Database, conversation_id: str, token: str, provider: Provider) -> None:
        """Keep response ownership outside framework configuration and checkpoint state."""
        self.db, self.conversation_id, self.token, self.provider = (
            db,
            conversation_id,
            token,
            provider,
        )

    def complete(self, invoke: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
        """Reserve before one framework invocation and settle every attempt exactly once."""
        conversation = memory.get(self.db, self.conversation_id)
        catalog = ToolCatalog(conversation)
        request = assemble(
            conversation,
            catalog.core,
            list(catalog.loaded.values()),
            workspace(self.db, conversation),
        )
        reservation = reserve(
            self.db,
            BudgetRequest(
                conversation_id=conversation.id,
                model=request.model,
                input_tokens=_input_bound(self.provider, request),
                max_output_tokens=request.max_output_tokens,
                limits=conversation.config.budget,
            ),
        )
        started = perf_counter()
        try:
            response = invoke(request)
        except Exception:
            self._settle(
                request,
                reservation.id,
                ModelResponse(stop_reason="provider_error"),
                started,
                billing_status="unknown",
            )
            raise
        self._settle(
            request,
            reservation.id,
            response,
            started,
            billing_status="actual" if response.usage_known else "unknown",
        )
        return response

    def _settle(
        self,
        request: ModelRequest,
        reservation_id: str,
        response: ModelResponse,
        started: float,
        *,
        billing_status: Literal["actual", "unknown"] = "actual",
    ) -> None:
        conversation = memory.append(self.db, self.conversation_id, self.token, model_call=True)
        trace = settle(
            self.db,
            reservation_id,
            TraceInput(
                conversation_id=conversation.id,
                turn=conversation.turns,
                model=request.model,
                provider=conversation.config.provider,
                segments=allocate_tokens(request.segments, response.usage.input_tokens),
                usage=response.usage,
                latency_ms=(perf_counter() - started) * 1000,
                stop_reason=response.stop_reason,
                tool_calls=len(response.tool_calls),
                billing_status=billing_status,
            ),
        )
        if trace.budget_exceeded:
            msg = "Observed provider consumption exceeded the available budget"
            raise BudgetError(msg)


def _input_bound(provider: Provider, request: ModelRequest) -> int:
    """Use exact offline demo accounting and conservative bounds for external providers."""
    tokens = sum(segment.tokens for segment in request.segments)
    return max(1, tokens // 4) if isinstance(provider, DemoProvider) else tokens
