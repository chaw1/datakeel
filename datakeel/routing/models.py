# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict provider routing configuration and frozen benchmark documents."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.routing_models import ModelTier, RouteBranch, TierState


class TierModels(BoundaryModel):
    """Require exactly the three supported model tiers."""

    simple: str = Field(min_length=1)
    multi_step: str = Field(min_length=1)
    high_risk: str = Field(min_length=1)


class ProviderModels(BoundaryModel):
    """Keep fallback links within their owning provider section."""

    tiers: TierModels
    fallbacks: dict[str, str] = Field(default_factory=dict[str, str])


class ModelRoutingConfig(BoundaryModel):
    """Validate the entire document without silently replacing invalid sections."""

    version: Literal[1]
    providers: dict[Literal["fake", "openai", "anthropic"], ProviderModels]


class IntentCase(BoundaryModel):
    """Identify the expected semantic result and routing branch of one input."""

    id: str
    source: str
    input: str
    expected_workflow: str | None
    expected_branch: RouteBranch


class TierCase(BoundaryModel):
    """Evaluate classification from only the three pre-call state components."""

    id: str
    input: TierState
    expected_tier: ModelTier


class IntentSuite(BoundaryModel):
    """Freeze a versioned set of intent labels independently of implementation."""

    version: Literal[1]
    cases: list[IntentCase]


class TierSuite(BoundaryModel):
    """Freeze a versioned set of model-tier labels."""

    version: Literal[1]
    cases: list[TierCase]
