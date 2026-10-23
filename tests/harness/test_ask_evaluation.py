# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify measured question tools, ordinal expectations, and controlled metric changes."""

from datakeel.core.ask_models import AskAnswer
from datakeel.core.harness_eval import ExpectedToolResult, ObservedToolResult
from datakeel.core.models import JsonDocument
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.harness.tool_assessment import tool_failures
from datakeel.ontology.models import FunctionResult


def test_metric_change_golden_measures_both_real_answers_and_revision_change() -> None:
    """A real reversible action changes SQL and values, independently of scripted prose."""
    source = next(case for case in load_cases() if case.id == "20-ask-updated-metric")
    result = run_case(source, "fake")
    assert result.passed, result.failures
    assert result.action_types == ["update_metric"]
    answers = [
        AskAnswer.model_validate(FunctionResult.model_validate(item.content.root).data)
        for item in result.tool_results
        if item.name == "ask_data"
    ]
    assert [answer.metric_card.definition.version for answer in answers if answer.metric_card] == [
        1,
        2,
    ]
    assert [answer.result.rows for answer in answers if answer.result] == [[[4979475]], [[5255975]]]
    assert all(answer.assertion_ids for answer in answers)
    assert "paid_amount" in str(answers[0].sql)
    assert "list_amount" in str(answers[1].sql)


def test_ordinal_tool_expectations_detect_reordered_or_missing_calls() -> None:
    """Separate schemas can require the before and after versions on repeated tool calls."""
    before = ObservedToolResult(
        name="ask_data", status="SUCCEEDED", content=JsonDocument({"version": 1}), asset_refs=[]
    )
    after = before.model_copy(update={"content": JsonDocument({"version": 2})})
    expected = ExpectedToolResult(
        name="ask_data",
        calls=2,
        call_index=1,
        asset_refs_required=False,
        content_schema=JsonDocument({"properties": {"version": {"const": 2}}}),
    )
    assert tool_failures([expected], [before, after]) == []
    assert any(
        "Tool content mismatch" in failure for failure in tool_failures([expected], [after, before])
    )
    failures = tool_failures([expected], [before])
    assert "Tool result count mismatch: ask_data" in failures
    assert "Tool result index missing: ask_data" in failures
