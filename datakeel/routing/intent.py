# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score declared multilingual concepts and verify bounded classifier suggestions."""

import re

from datakeel.actions.registry import action_definitions
from datakeel.core.routing_models import RouteCandidate, RouteDecision
from datakeel.routing.scopes import scope_for_workflow, workflow_scope
from datakeel.workflows.models import ApprovalStep, ToolStep, WorkflowDefinition

CLASSIFIER_CANDIDATE_LIMIT = 3


def normalize(text: str) -> str:
    """Match Unicode case-insensitively with normalized whitespace."""
    return " ".join(text.casefold().split())


def classifier_candidates(decision: RouteDecision) -> list[RouteCandidate]:
    """Bound classification to the three highest positive-scoring declared candidates."""
    return sorted(
        [item for item in decision.candidates if item.score > 0],
        key=lambda candidate: (-candidate.score, candidate.workflow_id),
    )[:CLASSIFIER_CANDIDATE_LIMIT]


def keyword_route(text: str, workflows: list[WorkflowDefinition]) -> RouteDecision:
    """Route clear complete matches directly and classify plausible partial matches."""
    normalized = normalize(text)
    definitions = {workflow.id: workflow for workflow in workflows}
    candidates = sorted(
        [
            RouteCandidate(workflow_id=workflow.id, score=_score(normalized, workflow, workflows))
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
            reason="partial_keyword_match" if top.score > 0 else "below_threshold",
            branch="classifier" if top.score > 0 else "free_agent",
            score=top.score,
            candidates=candidates,
        )
    second = max(
        (
            item.score
            for item in candidates[1:]
            if item.score >= definitions[item.workflow_id].triggers.threshold
            or _critical_match(normalized, definitions[item.workflow_id], workflows)
        ),
        default=0,
    )
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


def _excluded(text: str, workflow: WorkflowDefinition) -> bool:
    triggers = workflow.triggers
    request = re.sub(
        r"^(?:(?:(?:please|can you|could you|would you)\s+|请你|请|麻烦你|麻烦|帮我|给我)\s*)+",
        "",
        text,
    )
    return (
        any(_position(request, word) == 0 for word in triggers.excluded_prefixes)
        or any(_position(text, word) is not None for word in triggers.excluded_keywords)
        or _matches_groups(text, triggers.excluded_groups)
    )


def _matches_groups(text: str, groups: list[list[str]], *, inflections: bool = False) -> bool:
    position = _inflected_position if inflections else _position
    return any(all(position(text, term) is not None for term in group) for group in groups)


def _score(text: str, workflow: WorkflowDefinition, workflows: list[WorkflowDefinition]) -> float:
    text = scope_for_workflow(text, workflow, workflows)
    if _excluded(text, workflow):
        return 0
    triggers = workflow.triggers
    score = sum(
        all(_position(text, term) is not None for term in group) for group in triggers.keywords
    )
    if score:
        return score
    partial = max(
        sum(_position(text, term) is not None for term in group) / len(group)
        for group in triggers.keywords
    )
    semantic = 0.5 if _matches_groups(text, triggers.classification_groups, inflections=True) else 0
    return max(partial, semantic) * triggers.threshold


def _critical_match(
    text: str, workflow: WorkflowDefinition, workflows: list[WorkflowDefinition]
) -> bool:
    terms = workflow.triggers.verification_keywords or workflow.triggers.classification_keywords
    scoped = scope_for_workflow(text, workflow, workflows)
    return any(_inflected_position(scoped, term) is not None for term in terms)


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


def _inflected_position(text: str, expression: str) -> int | None:
    alternatives: list[str] = []
    for alternative in expression.split("|"):
        term = normalize(alternative)
        alternatives.append(term)
        ending = re.search(r"[a-z]+$", term)
        if ending is not None:
            word = ending[0]
            prefix = term[: ending.start()]
            past = word + "d" if word.endswith("e") else word + "ed"
            stem = word.removesuffix("e")
            alternatives.extend([prefix + past, prefix + stem + "ing"])
    return _position(text, "|".join(alternatives))


def classify_offline(
    text: str, candidates: list[RouteCandidate], workflows: list[WorkflowDefinition]
) -> str | None:
    """Choose the earliest eligible intent deterministically without external model calls."""
    normalized = normalize(text)
    bounded = sorted(candidates, key=lambda candidate: (-candidate.score, candidate.workflow_id))[
        :CLASSIFIER_CANDIDATE_LIMIT
    ]
    scores = {
        candidate.workflow_id: candidate.score for candidate in bounded if candidate.score > 0
    }
    ranked: list[tuple[bool, int, str]] = []
    for workflow in workflows:
        scope = workflow_scope(normalized, workflow, workflows)
        scoped = scope.text
        if workflow.id not in scores or _excluded(scoped, workflow):
            continue
        triggers = workflow.triggers
        groups = triggers.classification_groups
        partial = scores[workflow.id] < triggers.threshold
        if (
            partial
            and groups
            and not _matches_groups(scoped, [*groups, *triggers.keywords], inflections=True)
        ):
            continue
        signals = [term for group in groups for term in group] if partial else []
        positions = [
            position
            for word in [*triggers.classification_keywords, *signals]
            if (position := _inflected_position(scoped, word)) is not None
        ]
        if positions:
            ranked.append((scope.deferred, scope.position + min(positions), workflow.id))
    return min(ranked)[2] if ranked else None


def classified_route(
    decision: RouteDecision,
    selected: str | None,
    text: str = "",
    workflows: list[WorkflowDefinition] | None = None,
) -> RouteDecision:
    """Reject invented candidates and verify a selected workflow's literal entity or verb."""
    matching = next(
        (item for item in classifier_candidates(decision) if item.workflow_id == selected), None
    )
    audit = {
        "classifier_used": True,
        "classifier_selection": selected,
        "workflow_id": None,
        "requires_confirmation": False,
        "verification_passed": None,
    }
    if matching is None:
        return decision.model_copy(
            update={**audit, "branch": "free_agent", "reason": "classifier_abstained"}
        )
    workflow = next((item for item in workflows or [] if item.id == selected), None)
    if workflow is None:
        return decision.model_copy(
            update={**audit, "branch": "free_agent", "reason": "classifier_unverified"}
        )
    terms = workflow.triggers.verification_keywords or workflow.triggers.classification_keywords
    scoped = scope_for_workflow(normalize(text), workflow, workflows)
    verified = not _excluded(scoped, workflow) and any(
        _inflected_position(scoped, term) is not None for term in terms
    )
    if not verified:
        return decision.model_copy(
            update={
                **audit,
                "branch": "free_agent",
                "reason": "classifier_verification_failed",
                "verification_passed": False,
            }
        )
    return decision.model_copy(
        update={
            **audit,
            "workflow_id": matching.workflow_id,
            "score": matching.score,
            "reason": "classified",
            "verification_passed": True,
            "requires_confirmation": _writes_data(workflow),
        }
    )


def _writes_data(workflow: WorkflowDefinition) -> bool:
    actions = {action.id for action in action_definitions()}
    return any(
        isinstance(step, ApprovalStep) or (isinstance(step, ToolStep) and step.tool in actions)
        for step in workflow.steps
    )
