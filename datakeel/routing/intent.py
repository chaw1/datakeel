# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score declared multilingual trigger groups without running a workflow."""

import re

from datakeel.core.routing_models import RouteCandidate, RouteDecision
from datakeel.workflows.models import WorkflowDefinition


def normalize(text: str) -> str:
    """Match Unicode case-insensitively with normalized whitespace."""
    return " ".join(text.casefold().split())


def keyword_route(text: str, workflows: list[WorkflowDefinition]) -> RouteDecision:
    """Route only when the highest declared score clears its threshold and margin."""
    normalized = normalize(text)
    definitions = {workflow.id: workflow for workflow in workflows}
    candidates = sorted(
        [
            RouteCandidate(workflow_id=workflow.id, score=_score(normalized, workflow))
            for workflow in workflows
        ],
        key=lambda candidate: (-candidate.score, candidate.workflow_id),
    )
    if not candidates:
        return RouteDecision(reason="no_workflows", branch="free_agent", candidates=[])
    top = candidates[0]
    trigger = definitions[top.workflow_id].triggers
    if top.score < trigger.threshold:
        return RouteDecision(
            reason="below_threshold", branch="free_agent", score=top.score, candidates=candidates
        )
    second = candidates[1].score if len(candidates) > 1 else 0
    lead = top.score - second
    if lead >= trigger.margin:
        return RouteDecision(
            workflow_id=top.workflow_id,
            score=top.score,
            reason="keyword_margin_satisfied",
            branch="keyword",
            candidates=candidates,
        )
    return RouteDecision(
        score=top.score,
        reason="insufficient_keyword_margin",
        branch="classifier",
        candidates=candidates,
    )


def _score(text: str, workflow: WorkflowDefinition) -> float:
    triggers = workflow.triggers
    request = re.sub(
        r"^(?:(?:(?:please|can you|could you|would you)\s+|请你|请|麻烦你|麻烦|帮我|给我)\s*)+",
        "",
        text,
    )
    if any(_position(request, word) == 0 for word in triggers.excluded_prefixes):
        return 0
    if any(_position(text, word) is not None for word in triggers.excluded_keywords) or any(
        all(_position(text, term) is not None for term in group)
        for group in triggers.excluded_groups
    ):
        return 0
    return sum(
        all(_position(text, term) is not None for term in group) for group in triggers.keywords
    )


def _position(text: str, expression: str) -> int | None:
    positions: list[int] = []
    for alternative in expression.split("|"):
        term = normalize(alternative)
        prefix = r"(?<![a-z0-9_])" if term[0].isascii() and term[0].isalnum() else ""
        suffix = r"(?![a-z0-9_])" if term[-1].isascii() and term[-1].isalnum() else ""
        match = re.search(prefix + re.escape(term) + suffix, text)
        if match:
            positions.append(match.start())
    return min(positions) if positions else None


def classify_offline(
    text: str, candidates: list[RouteCandidate], workflows: list[WorkflowDefinition]
) -> str | None:
    """Choose the earliest declared classifier signal among keyword-qualified candidates."""
    normalized = normalize(text)
    scores = {candidate.workflow_id: candidate.score for candidate in candidates}
    ranked: list[tuple[int, str]] = []
    for workflow in workflows:
        if scores.get(workflow.id, 0) < workflow.triggers.threshold:
            continue
        positions = [
            position
            for word in workflow.triggers.classification_keywords
            if (position := _position(normalized, word)) is not None
        ]
        if positions:
            ranked.append((min(positions), workflow.id))
    return min(ranked)[1] if ranked else None


def classified_route(decision: RouteDecision, selected: str | None) -> RouteDecision:
    """Accept only a scored candidate and preserve reasons for classification abstention."""
    matching = next(
        (item for item in decision.candidates if item.workflow_id == selected and item.score > 0),
        None,
    )
    if matching is None:
        return decision.model_copy(
            update={"branch": "free_agent", "reason": "classifier_abstained"}
        )
    return decision.model_copy(
        update={
            "workflow_id": matching.workflow_id,
            "score": matching.score,
            "reason": "classified",
        }
    )
