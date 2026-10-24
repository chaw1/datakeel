# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable metering, trace, and persistent budget boundaries."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel
from datakeel.core.routing_models import ModelRouteDecision


class TokenUsage(BoundaryModel):
    """Count all input tokens once, with cache categories as input subsets."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_cache(self) -> Self:
        """Reject cache counts that exceed the inclusive input count."""
        if self.cache_read_tokens + self.cache_write_tokens > self.input_tokens:
            msg = "Cached tokens must be a subset of input tokens"
            raise ValueError(msg)
        return self


class TokenSegment(BoundaryModel):
    """Attribute input usage to a stable or volatile context segment."""

    name: str
    tokens: int = Field(ge=0)
    stable: bool = False


class BudgetLimits(BoundaryModel):
    """Bound actual plus reserved consumption for a conversation and UTC day."""

    conversation_tokens: int = Field(default=100_000, ge=0)
    daily_tokens: int = Field(default=1_000_000, ge=0)
    conversation_usd: Decimal = Field(default=Decimal(1), ge=0, allow_inf_nan=False)
    daily_usd: Decimal = Field(default=Decimal(10), ge=0, allow_inf_nan=False)


class BudgetRequest(BoundaryModel):
    """Reserve a conservative upper bound before a provider is invoked."""

    conversation_id: str = Field(min_length=1)
    model: str
    input_tokens: int = Field(ge=0)
    max_output_tokens: int = Field(ge=0)
    limits: BudgetLimits = Field(default_factory=BudgetLimits)


class BudgetReservation(BoundaryModel):
    """Identify a durable reservation that survives process restarts."""

    id: str
    conversation_id: str
    model: str
    day: str
    tokens: int
    cost_usd: Decimal
    status: Literal["RESERVED", "SETTLED", "REFUNDED", "REJECTED"]


class BudgetAccount(BoundaryModel):
    """Expose spent and outstanding resources without losing precision."""

    key: str
    token_limit: int
    usd_limit: Decimal
    used_tokens: int
    reserved_tokens: int
    spent_usd: Decimal
    reserved_usd: Decimal


class TraceInput(BoundaryModel):
    """Describe one completed or failed provider call before cost settlement."""

    conversation_id: str
    turn: int = Field(ge=1)
    model: str
    provider: str
    segments: list[TokenSegment]
    usage: TokenUsage
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    stop_reason: str
    tool_calls: int = Field(ge=0)
    billing_status: Literal["actual", "unknown"] = "actual"
    call_type: Literal["conversation", "intent_classifier", "extraction"] = "conversation"
    model_route: ModelRouteDecision | None = None
    accounting_conversation_id: str | None = None
    agent_path: str = "main"
    depth: int = Field(default=0, ge=0)
    parent_tool_call_id: str | None = None

    @model_validator(mode="after")
    def validate_segments(self) -> Self:
        """Keep context attribution exactly equal to the provider's input usage."""
        if sum(segment.tokens for segment in self.segments) != self.usage.input_tokens:
            msg = "Segment tokens must sum to input tokens"
            raise ValueError(msg)
        if self.billing_status == "unknown" and self.usage != TokenUsage():
            msg = "Unknown billing cannot claim observed token usage"
            raise ValueError(msg)
        return self


class ModelCallTrace(TraceInput):
    """Keep observed usage separate from conservative charges for unknown billing."""

    id: str
    reservation_id: str
    cost_usd: Decimal
    price_version: str
    created_at: datetime
    accounted_tokens: int = Field(default=0, ge=0)
    budget_exceeded: bool = False


class CostSummary(BoundaryModel):
    """Aggregate recorded calls by one stable reporting dimension."""

    key: str
    group_by: Literal["conversation", "day", "model"]
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    unknown_calls: int = Field(default=0, ge=0)
    unknown_cost_usd: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)
