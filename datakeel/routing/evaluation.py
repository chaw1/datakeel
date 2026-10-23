# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate frozen route labels with inspectable confusion matrices entirely offline."""

from pathlib import Path

import yaml
from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.routing.config import contract_path
from datakeel.routing.intent import classified_route, classify_offline, keyword_route
from datakeel.routing.models import IntentSuite, TierSuite
from datakeel.routing.tiers import classify_tier
from datakeel.workflows.loader import list_workflows


class RouteEvaluation(BoundaryModel):
    """Report exact workflow, branch, and model-tier agreement."""

    intent_total: int
    tier_total: int
    intent_correct: int
    tier_correct: int
    workflow_confusion: dict[str, dict[str, int]]
    branch_confusion: dict[str, dict[str, int]]
    tier_confusion: dict[str, dict[str, int]]
    failures: list[str] = Field(default_factory=list[str])

    @property
    def accuracy(self) -> float:
        """Count an intent as correct only when both workflow and branch match."""
        return (self.intent_correct + self.tier_correct) / (self.intent_total + self.tier_total)


def _record(matrix: dict[str, dict[str, int]], expected: str, actual: str) -> None:
    row = matrix.setdefault(expected, {})
    row[actual] = row.get(actual, 0) + 1


def evaluate_routes(directory: Path | None = None) -> RouteEvaluation:
    """Run the immutable intent and state-based tier corpora with the production rules."""
    path = directory or contract_path("routing")
    intents = IntentSuite.model_validate(yaml.safe_load((path / "intent-cases.yaml").read_text()))
    tiers = TierSuite.model_validate(yaml.safe_load((path / "model-tier-cases.yaml").read_text()))
    workflows = list_workflows()
    workflow_matrix: dict[str, dict[str, int]] = {}
    branch_matrix: dict[str, dict[str, int]] = {}
    tier_matrix: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    intent_correct = tier_correct = 0
    for case in intents.cases:
        result = keyword_route(case.input, workflows)
        if result.branch == "classifier":
            result = classified_route(
                result, classify_offline(case.input, result.candidates, workflows)
            )
        _record(
            workflow_matrix,
            case.expected_workflow or "free_agent",
            result.workflow_id or "free_agent",
        )
        _record(branch_matrix, case.expected_branch, result.branch)
        if (result.workflow_id, result.branch) == (case.expected_workflow, case.expected_branch):
            intent_correct += 1
        else:
            failures.append(
                f"{case.id}: expected {case.expected_workflow}/{case.expected_branch}, "
                f"got {result.workflow_id}/{result.branch}"
            )
    for case in tiers.cases:
        tier = classify_tier(case.input)
        _record(tier_matrix, case.expected_tier, tier)
        if tier == case.expected_tier:
            tier_correct += 1
        else:
            failures.append(f"{case.id}: expected {case.expected_tier}, got {tier}")
    return RouteEvaluation(
        intent_total=len(intents.cases),
        tier_total=len(tiers.cases),
        intent_correct=intent_correct,
        tier_correct=tier_correct,
        workflow_confusion=workflow_matrix,
        branch_confusion=branch_matrix,
        tier_confusion=tier_matrix,
        failures=failures,
    )
