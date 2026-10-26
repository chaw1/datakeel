# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable intent suggestions and observable model-selection decisions."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel

ModelTier = Literal["simple", "multi_step", "high_risk"]
RouteBranch = Literal["keyword", "classifier", "free_agent"]


class TierState(BoundaryModel):
    """Describe only state available before the current model invocation."""

    loaded_tools: list[str] = Field(default_factory=list[str])
    response_has_plan: bool = False
    response_has_tool_result: bool = False


class RouteCandidate(BoundaryModel):
    """Expose the deterministic keyword score for one registered workflow."""

    workflow_id: str
    score: float = Field(ge=0)


class RouteInputs(BoundaryModel):
    """Prefill only the conversation's explicitly selected dataset."""

    dataset_id: str | None = None


class RouteDecision(BoundaryModel):
    """Persist an auditable suggestion without authorizing workflow execution."""

    workflow_id: str | None = None
    score: float = Field(default=0, ge=0)
    reason: str
    branch: RouteBranch
    candidates: list[RouteCandidate]
    inputs: RouteInputs = Field(default_factory=RouteInputs)
    classifier_used: bool = False
    classifier_selection: str | None = None
    verification_passed: bool | None = None
    requires_confirmation: bool = False


class ModelRouteDecision(BoundaryModel):
    """Record the selected tier, override policy, and one provider attempt."""

    tier: ModelTier
    model: str
    pinned: bool
    fallback_reason: str | None = None
    attempt: int = Field(default=1, ge=1, le=3)
