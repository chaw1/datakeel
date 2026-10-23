# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Settle every classified or conversational provider attempt independently."""

from collections.abc import Callable
from time import perf_counter
from typing import Literal

from pydantic import Field

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.context_tokens import allocate_tokens
from datakeel.core.errors import BudgetError
from datakeel.core.harness_models import BudgetLimits, BudgetRequest, TraceInput
from datakeel.core.models import BoundaryModel
from datakeel.core.routing_models import ModelRouteDecision
from datakeel.routing.config import price_for
from datakeel.storage.budget_service import reserve
from datakeel.storage.database import Database
from datakeel.storage.harness_service import settle


class CallContext(BoundaryModel):
    """Carry immutable billing identity separately from request content and response ownership."""

    conversation_id: str
    turn: int = Field(ge=1)
    provider: str
    limits: BudgetLimits
    call_type: Literal["conversation", "intent_classifier"] = "conversation"
    input_divisor: int = Field(default=1, ge=1)
    accounting_conversation_id: str | None = None
    agent_path: str = "main"
    depth: int = 0
    parent_tool_call_id: str | None = None


class ModelAccount:
    """Count actual provider attempts while preserving one reservation per invocation."""

    def __init__(self, db: Database, context: CallContext) -> None:
        """Keep transient attempt count outside persisted conversation turns."""
        self.db, self.context, self.attempts = db, context, 0

    def complete(
        self,
        request: ModelRequest,
        invoke: Callable[[ModelRequest], ModelResponse],
        route: ModelRouteDecision | None = None,
    ) -> ModelResponse:
        """Reserve before invocation and settle failed or successful usage exactly once."""
        version, price = price_for(request.model)
        reservation = reserve(
            self.db,
            BudgetRequest(
                conversation_id=self.context.accounting_conversation_id
                or self.context.conversation_id,
                model=request.model,
                input_tokens=max(
                    1,
                    sum(segment.tokens for segment in request.segments)
                    // self.context.input_divisor,
                ),
                max_output_tokens=request.max_output_tokens,
                limits=self.context.limits,
            ),
            version,
            price,
        )
        self.attempts += 1
        started = perf_counter()
        try:
            response = invoke(request)
        except Exception:
            self._settle_failure(request, reservation.id, started, route)
            raise
        self._settle(request, reservation.id, response, started, route)
        return response

    def _settle_failure(
        self,
        request: ModelRequest,
        reservation_id: str,
        started: float,
        route: ModelRouteDecision | None,
    ) -> None:
        self._settle(
            request,
            reservation_id,
            ModelResponse(stop_reason="provider_error", usage_known=False),
            started,
            route,
        )

    def _settle(
        self,
        request: ModelRequest,
        reservation_id: str,
        response: ModelResponse,
        started: float,
        route: ModelRouteDecision | None,
    ) -> None:
        trace = settle(
            self.db,
            reservation_id,
            TraceInput(
                conversation_id=self.context.conversation_id,
                turn=self.context.turn,
                model=request.model,
                provider=self.context.provider,
                segments=allocate_tokens(request.segments, response.usage.input_tokens),
                usage=response.usage,
                latency_ms=(perf_counter() - started) * 1000,
                stop_reason=response.stop_reason,
                tool_calls=len(response.tool_calls),
                billing_status="actual" if response.usage_known else "unknown",
                call_type=self.context.call_type,
                model_route=route,
                accounting_conversation_id=self.context.accounting_conversation_id,
                agent_path=self.context.agent_path,
                depth=self.context.depth,
                parent_tool_call_id=self.context.parent_tool_call_id,
            ),
        )
        if trace.budget_exceeded:
            msg = "Observed provider consumption exceeded the available budget"
            raise BudgetError(msg)
