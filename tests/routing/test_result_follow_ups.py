# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A request may ask for its own outcome; only questions about the workflow itself stop it."""

import pytest

from datakeel.core.routing_models import RouteDecision
from datakeel.routing.intent import classified_route, classify_offline, keyword_route
from datakeel.routing.questions import asks_about_workflow, requested_text, result_split
from datakeel.workflows.loader import list_workflows
from tests.routing.paraphrase_cases import (
    READ_ONLY_OR_POSTPONED,
    RESULT_FOLLOW_UP_REQUESTS,
    WORKFLOW_FOCUS_FOLLOW_UPS,
)


def _route(message: str) -> RouteDecision:
    """Route with the keyword rules, then the deterministic offline classifier."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    if decision.branch != "classifier":
        return decision
    choice = classify_offline(message, decision.candidates, workflows)
    return classified_route(decision, choice, message, workflows)


def _forced(message: str, workflow_id: str) -> RouteDecision:
    """Verify a model's choice of one workflow among every positively scored candidate."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    candidates = [item.model_copy(update={"score": 0.5}) for item in decision.candidates]
    forced = decision.model_copy(update={"branch": "classifier", "candidates": candidates})
    return classified_route(forced, workflow_id, message, workflows)


def _assert_started(message: str, expected: str) -> None:
    """Start exactly the requested workflow and accept the same choice from a model."""
    decision = _route(message)
    assert decision.reason != "workflow_question", message
    assert decision.workflow_id == expected, (message, decision.reason, decision.candidates)
    assert _forced(message, expected).verification_passed is True, message


def _assert_refused(message: str) -> None:
    """Treat the message as a question about the workflow, even when a model picks one."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    assert decision.reason == "workflow_question", message
    assert _route(message).workflow_id is None
    for workflow in workflows:
        assert _forced(message, workflow.id).workflow_id is None, (message, workflow.id)


@pytest.mark.parametrize(("message", "expected"), RESULT_FOLLOW_UP_REQUESTS)
def test_requests_that_ask_for_their_outcome_start_the_workflow(
    message: str, expected: str
) -> None:
    """An imperative request linked to a question about its result is still a request."""
    _assert_started(message, expected)


def test_no_outcome_follow_up_turns_a_request_into_a_question() -> None:
    """One sweep over the outcome follow-ups for guard mutations."""
    for message, expected in RESULT_FOLLOW_UP_REQUESTS:
        _assert_started(message, expected)


@pytest.mark.parametrize("message", WORKFLOW_FOCUS_FOLLOW_UPS)
def test_follow_ups_about_the_workflow_itself_stay_questions(message: str) -> None:
    """Approval, duration, undo, past runs, approvers and effects keep the guard closed."""
    _assert_refused(message)


def test_no_follow_up_about_the_workflow_itself_starts_it() -> None:
    """One sweep over workflow-focused follow-ups for guard mutations."""
    for message in WORKFLOW_FOCUS_FOLLOW_UPS:
        _assert_refused(message)


@pytest.mark.parametrize("message", READ_ONLY_OR_POSTPONED)
def test_read_only_and_postponed_requests_never_start_or_verify(message: str) -> None:
    """Colloquial disposal vocabulary under "only look" or "hold off" never starts a run."""
    assert _route(message).workflow_id is None, message
    for workflow in list_workflows():
        assert _forced(message, workflow.id).workflow_id is None, (message, workflow.id)


@pytest.mark.parametrize(
    ("sentence", "linked"),
    [
        ("Clean up the junk samples and then tell me how many were removed.", True),
        ("清理低质样本, 然后告诉我删了几个。", True),
        ("Is it safe to purge the junk samples and then rerun?", False),
        ("清理低质样本需要审批吗?", False),
        ("Clean up the junk samples and check quality again.", False),
        ("合并数据集再看看有多少", True),
    ],
)
def test_outcome_links_need_an_imperative_head_and_a_question_tail(
    sentence: str, *, linked: bool
) -> None:
    """A link splits only a non-question request from a following question."""
    assert (result_split(sentence) is not None) is linked


def test_outcome_question_words_are_blanked_but_its_content_is_kept() -> None:
    """The outcome joins the request clause with offsets kept and its question form removed."""
    message = "把口径换成含税\uff0c再看看数字差了多少"
    kept = requested_text(message)
    assert len(kept) == len(message)
    assert "\uff0c" not in kept
    assert "多少" not in kept
    assert "看看" not in kept
    assert "差了" in kept
    assert not asks_about_workflow(message)


def test_a_report_rebuild_reaches_the_classifier_and_verifies() -> None:
    """Rebuilding the health report scores the health check without any rule start."""
    message = "Rebuild the health report for ds-x and tell me how many files failed?"
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    assert decision.branch == "classifier"
    assert any(
        item.workflow_id == "dataset-health" and item.score > 0 for item in decision.candidates
    )
    assert classify_offline(message, decision.candidates, workflows) in {None, "dataset-health"}
    chosen = classified_route(decision, "dataset-health", message, workflows)
    assert chosen.workflow_id == "dataset-health"
    assert chosen.verification_passed is True
