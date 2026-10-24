# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge evaluations retain independent metric totals and inspect production receipts."""

from datakeel.core.knowledge_eval import KnowledgeExpectation
from datakeel.harness.knowledge_checks import knowledge_failures
from datakeel.harness.knowledge_evaluation import run_evaluation


def test_both_knowledge_states_preserve_original_metric_benchmark() -> None:
    """All initial/reviewed cases and six route counterexamples pass with real source evidence."""
    report = run_evaluation()
    assert len(report.questions) == 20
    assert all(item.correct and item.evidence_complete for item in report.questions)
    assert report.threshold_met
    assert report.knowledge is not None
    assert report.knowledge.threshold_met
    assert [(state.state, state.passed, state.total) for state in report.knowledge.states] == [
        ("initial", 23, 23),
        ("reviewed", 23, 23),
    ]
    assert all(
        item.answer is not None for state in report.knowledge.states for item in state.questions
    )
    initial = report.knowledge.states[0].questions[0].answer
    assert initial is not None
    assert initial.knowledge is not None
    expected = KnowledgeExpectation(subject="出货额")
    broken = initial.model_copy(update={"assertions": ()})
    assert any("citations" in failure for failure in knowledge_failures(expected, broken, None))
    assert "subject" in knowledge_failures(KnowledgeExpectation(subject="wrong"), initial, None)
    assert "Missing knowledge payload" in knowledge_failures(
        expected,
        initial.model_copy(update={"knowledge": None}),
        None,
    )
