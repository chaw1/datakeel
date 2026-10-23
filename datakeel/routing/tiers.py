# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Choose models from observable state without inspecting future model output."""

from datakeel.actions.registry import POLICIES
from datakeel.core.agent_models import ConversationCreate
from datakeel.core.routing_models import ModelRouteDecision, ModelTier, TierState
from datakeel.routing.config import fallback_chain
from datakeel.routing.models import ModelRoutingConfig


def classify_tier(state: TierState) -> ModelTier:
    """Prioritize loaded controlled actions and plans over prior tool results."""
    if state.response_has_plan or any(name in POLICIES for name in state.loaded_tools):
        return "high_risk"
    return "multi_step" if state.response_has_tool_result else "simple"


def select_model(
    session: ConversationCreate, state: TierState, config: ModelRoutingConfig
) -> ModelRouteDecision:
    """Honor fake and explicit session models while still exposing the selected tier."""
    tier = classify_tier(state)
    pinned = session.provider == "fake" or session.model != "auto"
    model = session.model if pinned else getattr(config.providers[session.provider].tiers, tier)
    return ModelRouteDecision(tier=tier, model=model, pinned=pinned)


def model_chain(
    session: ConversationCreate, selected: ModelRouteDecision, config: ModelRoutingConfig
) -> list[str]:
    """Keep fake calls fixed and permit only validated same-provider fallback links."""
    if session.provider == "fake":
        return [selected.model]
    return fallback_chain(config.providers[session.provider], selected.model)
