# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen routing accuracy and independent single-step false-positive checks."""

from pathlib import Path

import pytest
import yaml

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.routing_models import RouteCandidate, TierState
from datakeel.routing.config import contract_path, load_config
from datakeel.routing.evaluation import evaluate_routes
from datakeel.routing.intent import classified_route, classify_offline, keyword_route
from datakeel.routing.models import IntentSuite
from datakeel.routing.tiers import classify_tier, model_chain, select_model
from datakeel.workflows.loader import list_workflows
from datakeel.workflows.models import WorkflowTriggers
from tests.routing.intent_helpers import resolve_route


def test_frozen_routes_when_evaluated_match_every_label() -> None:
    """Require both workflow and branch accuracy, plus all state-based tier cases."""
    result = evaluate_routes()
    assert result.failures == []
    assert (result.intent_correct, result.tier_correct, result.accuracy) == (116, 14, 1)
    assert {name: (suite.correct, suite.total) for name, suite in result.intent_suites.items()} == {
        "intent-cases.yaml": (75, 75),
        "intent-regression.yaml": (41, 41),
    }
    assert result.branch_confusion["classifier"] == {"classifier": 6}


def test_golden_inputs_when_routed_keep_frozen_workflow_and_branch() -> None:
    """Keep all 57 original user inputs and final decisions exactly represented."""
    suite = IntentSuite.model_validate(
        yaml.safe_load(contract_path("routing/intent-cases.yaml").read_text())
    )
    golden = [case for case in suite.cases if case.source.startswith("contracts/golden/")]
    assert len(golden) == 57
    for case in golden:
        filename, turn = case.source.split("#turns/")
        document = yaml.safe_load(Path(filename).read_text())
        assert document["turns"][int(turn)]["input"] == case.input
        result = resolve_route(case.input)
        assert (result.workflow_id, result.branch) == (case.expected_workflow, case.expected_branch)


@pytest.mark.parametrize(
    "message",
    [
        "Show the current data quality score.",
        "请列出低于三十分的图片。",
        "Only quarantine the selected items.",
        "删除选中的两张文件。",
        "Get task status for the latest pipeline job.",
        "Update the metric measure column to net_sales.",
        "更改指标度量字段为净支付金额。",
        "Which fields participate in this metric?",
        "Explain the new dataset health check.",
        "不要运行低质样本清理。",
        "Do not start the metric definition change workflow.",
        "What does low-quality sample cleanup mean?",
        "这批数据的标注证据在哪里?",
        "请修改指标名称为累计销售。",
        "查一下本月的订单总量。",
        "Run the preprocessing pipeline for this dataset.",
    ],
)
def test_single_step_holdout_when_no_full_workflow_requested_stays_free(message: str) -> None:
    """Independent bilingual requests must not gain extra workflow actions."""
    decision = resolve_route(message)
    assert (decision.workflow_id, decision.branch) == (None, "free_agent")


def test_margin_when_two_workflows_tie_requires_classifier() -> None:
    """Removing the score margin must produce an assertion failure in this test."""
    workflows = [
        workflow.model_copy(
            update={
                "triggers": WorkflowTriggers(
                    keywords=[["shared signal"]], classification_keywords=[workflow.id]
                )
            }
        )
        for workflow in list_workflows()[:2]
    ]
    result = keyword_route("shared signal", workflows)
    assert result.branch == "classifier"
    assert result.workflow_id is None


def test_classifier_when_no_declared_signal_abstains() -> None:
    """A deterministic classifier can use only declared vocabulary in qualified candidates."""
    workflows = list_workflows()
    candidates = [RouteCandidate(workflow_id=workflow.id, score=1) for workflow in workflows]
    assert classify_offline("Unrelated material", candidates, workflows) is None
    assert classify_offline("dataset health check", [], workflows) is None
    decision = keyword_route("no match", workflows)
    assert classified_route(decision, "invented-workflow").branch == "free_agent"
    assert keyword_route("anything", []).reason == "no_workflows"


def test_keyword_matching_when_case_and_whitespace_vary_is_stable() -> None:
    """Normalization preserves phrase matching without requiring a tokenizer."""
    result = keyword_route("Please RUN a NEW\nDATASET   HEALTH CHECK tomorrow.", list_workflows())
    assert result.workflow_id == "dataset-health"
    only = list_workflows()[:1]
    result = keyword_route(only[0].triggers.keywords[0][0], only)
    assert result.candidates[0].workflow_id == only[0].id


def test_tier_when_override_or_auto_preserves_selection_policy() -> None:
    """Only non-fake auto sessions use tier mappings; state still determines their tier."""
    config = load_config()
    state = TierState(loaded_tools=["delete_files"], response_has_tool_result=True)
    assert classify_tier(state) == "high_risk"
    for provider, model, pinned in [
        ("fake", "fake-script", True),
        ("openai", "custom", True),
        ("openai", "auto", False),
    ]:
        session = ConversationCreate.model_validate({"provider": provider, "model": model})
        selected = select_model(session, state, config)
        assert selected.pinned is pinned
        assert selected.tier == "high_risk"
        assert selected.model == ("gpt-4.1-mini" if model == "auto" else model)
        assert model_chain(session, selected, config) == [selected.model]
