# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Partial intent recall, bounded choices, and post-classifier literal verification."""

import json

import pytest

from datakeel.core.routing_models import RouteCandidate, RouteDecision
from datakeel.routing.classifier import classification_request
from datakeel.routing.intent import classified_route, classify_offline, keyword_route
from datakeel.workflows.loader import list_workflows
from datakeel.workflows.models import WorkflowTriggers
from tests.routing.recall_cases import NEGATIVE_CASES, POSITIVE_CASES


def test_partial_group_when_custom_workflow_has_one_signal_reaches_classifier() -> None:
    """Legacy declarations need no semantic group additions to classify a partial match."""
    workflow = list_workflows()[0].model_copy(
        update={
            "triggers": WorkflowTriggers(
                keywords=[["inspect", "records"]], classification_keywords=["inspect"]
            )
        }
    )
    decision = keyword_route("inspect", [workflow])
    assert decision.branch == "classifier"
    assert decision.score == 0.5
    selected = classify_offline("inspect", decision.candidates, [workflow])
    result = classified_route(decision, selected, "inspect", [workflow])
    assert result.workflow_id == workflow.id
    assert result.verification_passed is True


@pytest.mark.parametrize(("message", "expected"), POSITIVE_CASES)
def test_novel_composition_when_rules_are_partial_uses_verified_classifier(
    message: str, expected: str
) -> None:
    """Unseen whole utterances require no exact phrase additions to direct-routing rules."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    assert decision.branch == "classifier"
    assert 0 < decision.score < 1
    selected = classify_offline(message, decision.candidates, workflows)
    assert classify_offline(message, decision.candidates, list(reversed(workflows))) == selected
    result = classified_route(decision, selected, message, workflows)
    assert result.workflow_id == expected
    assert result.classifier_used is True
    assert result.classifier_selection == expected
    assert result.verification_passed is True
    assert result.requires_confirmation is True
    assert result.candidates == decision.candidates


@pytest.mark.parametrize("message", NEGATIVE_CASES)
def test_nearby_information_negation_or_single_step_when_routed_never_selects_workflow(
    message: str,
) -> None:
    """Entity overlap must not authorize the additional actions in a bundled workflow."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    if decision.branch == "classifier":
        decision = classified_route(
            decision,
            classify_offline(message, decision.candidates, workflows),
            message,
            workflows,
        )
    assert decision.workflow_id is None
    assert decision.branch == "free_agent"


def test_classifier_candidate_limit_when_four_positive_scores_rejects_fourth() -> None:
    """The prompt, offline selection and reply allowlist share a three-candidate bound."""
    workflows = [
        list_workflows()[0].model_copy(
            update={
                "id": f"choice-{number}",
                "triggers": WorkflowTriggers(
                    keywords=[["shared"]],
                    classification_keywords=[f"signal-{number}"],
                    verification_keywords=["shared"],
                ),
            }
        )
        for number in range(4)
    ]
    decision = RouteDecision(
        reason="partial_keyword_match",
        branch="classifier",
        candidates=[RouteCandidate(workflow_id=workflow.id, score=0.5) for workflow in workflows],
    )
    prompt = classification_request("fake-script", "shared signal-3", decision, workflows)
    choices = json.loads(prompt.messages[0].content.split("Workflows: ", 1)[1])
    assert [choice["id"] for choice in choices] == ["choice-0", "choice-1", "choice-2"]
    assert classify_offline("shared signal-3", decision.candidates, workflows) is None
    result = classified_route(decision, "choice-3", "shared", workflows)
    assert result.workflow_id is None
    assert result.classifier_selection == "choice-3"
    assert result.reason == "classifier_abstained"


def test_classifier_verification_when_candidate_has_no_literal_anchor_rejects() -> None:
    """Even a replayed valid candidate id cannot bypass the entity-or-verb check."""
    workflows = list_workflows()
    decision = RouteDecision(
        reason="partial_keyword_match",
        branch="classifier",
        candidates=[RouteCandidate(workflow_id="dataset-health", score=0.5)],
    )
    result = classified_route(decision, "dataset-health", "Unrelated content.", workflows)
    assert result.workflow_id is None
    assert result.branch == "free_agent"
    assert result.classifier_selection == "dataset-health"
    assert result.verification_passed is False
    assert result.requires_confirmation is False
    assert result.reason == "classifier_verification_failed"


@pytest.mark.parametrize("message", ["dataset_archive", "Do not audit this dataset."])
def test_classifier_verification_when_embedded_id_or_negation_rejects(message: str) -> None:
    """The final check uses both literal token boundaries and the same exclusion rules."""
    decision = RouteDecision(
        reason="partial_keyword_match",
        branch="classifier",
        candidates=[RouteCandidate(workflow_id="dataset-health", score=0.5)],
    )
    assert (
        classified_route(decision, "dataset-health", message, list_workflows()).workflow_id is None
    )


def test_classifier_when_definition_is_missing_cannot_skip_verification() -> None:
    """Missing workflow metadata produces abstention rather than an unverified suggestion."""
    decision = RouteDecision(
        reason="partial_keyword_match",
        branch="classifier",
        candidates=[RouteCandidate(workflow_id="dataset-health", score=0.5)],
    )
    result = classified_route(decision, "dataset-health")
    assert result.workflow_id is None
    assert result.reason == "classifier_unverified"


def test_classifier_when_rechecking_stale_decision_clears_previous_workflow() -> None:
    """Abstention cannot retain a previously verified write suggestion or confirmation flag."""
    decision = RouteDecision(
        workflow_id="dataset-health",
        score=1,
        reason="classified",
        branch="classifier",
        requires_confirmation=True,
        verification_passed=True,
        candidates=[RouteCandidate(workflow_id="dataset-health", score=1)],
    )
    result = classified_route(decision, "unknown", "dataset", list_workflows())
    assert result.workflow_id is None
    assert result.requires_confirmation is False
    assert result.verification_passed is None


def test_classifier_when_legacy_workflow_is_read_only_requires_no_confirmation() -> None:
    """Old definitions can use classification literals as their critical verification words."""
    workflow = list_workflows()[0]
    workflow = workflow.model_copy(
        update={
            "triggers": WorkflowTriggers(
                keywords=[["shared"]], classification_keywords=["checkup"]
            ),
            "steps": [step for step in workflow.steps if step.id in {"quality", "healthy"}],
        }
    )
    decision = RouteDecision(
        reason="insufficient_keyword_margin",
        branch="classifier",
        candidates=[RouteCandidate(workflow_id=workflow.id, score=1)],
    )
    result = classified_route(decision, workflow.id, "checkup", [workflow])
    assert result.verification_passed is True
    assert result.requires_confirmation is False


def test_classifier_when_workflow_has_only_approval_step_requires_confirmation() -> None:
    """An approval node independently requires confirmation even without a tool write node."""
    workflow = list_workflows()[1]
    workflow = workflow.model_copy(
        update={
            "triggers": WorkflowTriggers(
                keywords=[["shared"]], classification_keywords=["cleanup"]
            ),
            "steps": [step for step in workflow.steps if step.type == "approval"],
        }
    )
    decision = RouteDecision(
        reason="insufficient_keyword_margin",
        branch="classifier",
        candidates=[RouteCandidate(workflow_id=workflow.id, score=1)],
    )
    result = classified_route(decision, workflow.id, "cleanup", [workflow])
    assert result.verification_passed is True
    assert result.requires_confirmation is True
