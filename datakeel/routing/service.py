# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Meter optional intent classification without owning conversation turns or execution."""

from functools import lru_cache

import httpx
from pydantic import ValidationError as ModelValidationError

from datakeel.core.agent_models import Conversation, Provider
from datakeel.core.errors import DatakeelError
from datakeel.core.routing_models import ModelRouteDecision, RouteDecision, RouteInputs, TierState
from datakeel.routing.accounting import CallContext, ModelAccount
from datakeel.routing.classifier import OfflineClassifier, classification_request
from datakeel.routing.config import load_config
from datakeel.routing.intent import classified_route, keyword_route
from datakeel.routing.tiers import select_model
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces
from datakeel.workflows.loader import list_workflows
from datakeel.workflows.models import WorkflowDefinition


@lru_cache(maxsize=1)
def _workflows() -> list[WorkflowDefinition]:
    return list_workflows()


def route_message(db: Database, conversation: Conversation, provider: Provider) -> RouteDecision:
    """Classify only ambiguous messages and fail open to the normal Agent response."""
    text = next(
        message.content for message in reversed(conversation.messages) if message.role == "user"
    )
    workflows = _workflows()
    decision = keyword_route(text, workflows).model_copy(
        update={"inputs": RouteInputs(dataset_id=conversation.config.dataset_id)}
    )
    if decision.branch != "classifier":
        return decision
    selected = select_model(conversation.config, TierState(), load_config())
    request = classification_request(selected.model, text, decision, workflows)
    classifier = (
        OfflineClassifier(decision, workflows)
        if conversation.config.provider == "fake"
        else provider
    )
    account = ModelAccount(
        db,
        CallContext(
            conversation_id=conversation.id,
            turn=conversation.turns + 1,
            provider=conversation.config.provider,
            limits=conversation.config.budget,
            call_type="intent_classifier",
        ),
    )
    try:
        response = account.complete(request, classifier.complete)
    except (DatakeelError, httpx.HTTPError, ModelValidationError, ValueError) as error:
        return decision.model_copy(
            update={
                "branch": "free_agent",
                "reason": f"classifier_unavailable:{type(error).__name__}",
            }
        )
    return classified_route(decision, response.content.strip())


def model_decisions(
    db: Database, conversation_id: str, after_turn: int
) -> list[ModelRouteDecision]:
    """Expose only this response's conversational attempts after existing stream events."""
    return [
        trace.model_route
        for trace in list_traces(db, conversation_id)
        if trace.turn > after_turn
        and trace.call_type == "conversation"
        and trace.model_route is not None
    ]
