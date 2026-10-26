# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve the complete production route without provider or database fixtures."""

from datakeel.core.routing_models import RouteDecision
from datakeel.routing.intent import classified_route, classify_offline, keyword_route
from datakeel.workflows.loader import list_workflows


def resolve_route(text: str) -> RouteDecision:
    """Apply the same offline classification and final verification as the service."""
    workflows = list_workflows()
    decision = keyword_route(text, workflows)
    if decision.branch == "classifier":
        return classified_route(
            decision, classify_offline(text, decision.candidates, workflows), text, workflows
        )
    return decision
