# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Concept groups recall paraphrased requests; questions about a workflow never start it."""

import json

import pytest
from pydantic import ValidationError

from datakeel.core.routing_models import RouteDecision
from datakeel.routing.classifier import classification_request
from datakeel.routing.concepts import inflected_position
from datakeel.routing.intent import classified_route, classify_offline, keyword_route
from datakeel.routing.questions import asks_about_workflow, requested_text
from datakeel.workflows.loader import list_workflows
from datakeel.workflows.models import WorkflowConcepts, WorkflowTriggers
from tests.routing.paraphrase_cases import (
    NEGATIVE_MESSAGES,
    POSITIVE_REQUESTS,
    WORKFLOW_QUESTIONS,
)


def _route(message: str, selected: str | None = None) -> RouteDecision:
    """Route with the offline classifier, or with a fixed model choice when one is given."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    if decision.branch != "classifier":
        return decision
    choice = selected or classify_offline(message, decision.candidates, workflows)
    return classified_route(decision, choice, message, workflows)


@pytest.mark.parametrize(("message", "expected"), POSITIVE_REQUESTS)
def test_paraphrased_requests_reach_the_classifier_and_pass_verification(
    message: str, expected: str
) -> None:
    """Rules give a partial score, and a model choosing correctly is verified by concepts."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    assert decision.branch == "classifier"
    assert 0 < decision.score < 1
    assert expected in {item.workflow_id for item in decision.candidates if item.score > 0}
    chosen = _route(message, expected)
    assert chosen.workflow_id == expected
    assert chosen.verification_passed is True
    assert chosen.requires_confirmation is True


@pytest.mark.parametrize(("message", "expected"), POSITIVE_REQUESTS)
def test_offline_classifier_is_deterministic_and_never_picks_another_workflow(
    message: str, expected: str
) -> None:
    """The local classifier returns the requested workflow regardless of declaration order."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    selected = classify_offline(message, decision.candidates, workflows)
    assert classify_offline(message, decision.candidates, list(reversed(workflows))) == selected
    assert selected == expected


_QUESTION_REQUEST_PAIRS = [
    ("清理低质样本需要审批吗?", "清理低质样本。", "low-quality-cleanup"),
    (
        "Does the dataset health check need approval?",
        "Run a dataset health check.",
        "dataset-health",
    ),
    ("要多久才能做完数据集体检?", "做数据集体检。", "dataset-health"),
]


def _assert_never_started(message: str) -> None:
    """Neither the rules nor the offline classifier start anything for the message."""
    workflows = list_workflows()
    decision = _route(message)
    assert decision.workflow_id is None, message
    assert decision.branch == "free_agent", message
    keyword = keyword_route(message, workflows)
    assert classify_offline(message, keyword.candidates, workflows) is None, message


def _assert_unverifiable(message: str) -> None:
    """Refuse a workflow question at scoring and again when a model forces any choice."""
    workflows = list_workflows()
    decision = keyword_route(message, workflows)
    assert decision.reason == "workflow_question", message
    assert all(item.score == 0 for item in decision.candidates)
    forced = decision.model_copy(
        update={
            "branch": "classifier",
            "candidates": [item.model_copy(update={"score": 0.5}) for item in decision.candidates],
        }
    )
    for workflow in workflows:
        result = classified_route(forced, workflow.id, message, workflows)
        assert result.workflow_id is None, (message, workflow.id)
        assert result.verification_passed is False


def _assert_question_refused(question: str, request_text: str, workflow_id: str) -> None:
    """Start from the request wording and refuse the same vocabulary asked as a question."""
    workflows = list_workflows()
    assert keyword_route(question, workflows).workflow_id is None, question
    started = keyword_route(request_text, workflows)
    assert started.workflow_id == workflow_id
    assert started.branch == "keyword"


@pytest.mark.parametrize("message", NEGATIVE_MESSAGES)
def test_questions_and_near_misses_never_start_a_workflow(message: str) -> None:
    """Neither the rules nor the offline classifier start anything for these messages."""
    _assert_never_started(message)


def test_no_negative_message_starts_a_workflow() -> None:
    """One sweep over every negative message for guard mutations."""
    for message in NEGATIVE_MESSAGES:
        _assert_never_started(message)


@pytest.mark.parametrize("message", WORKFLOW_QUESTIONS)
def test_questions_about_a_workflow_cannot_be_verified_even_if_a_model_selects_one(
    message: str,
) -> None:
    """The question guard runs before scoring and again inside post-classifier verification."""
    _assert_unverifiable(message)


def test_no_workflow_question_passes_verification() -> None:
    """One sweep over every workflow question for guard mutations."""
    for message in WORKFLOW_QUESTIONS:
        _assert_unverifiable(message)


@pytest.mark.parametrize(("question", "request_text", "workflow_id"), _QUESTION_REQUEST_PAIRS)
def test_full_keyword_matches_start_only_when_not_asked_as_a_question(
    question: str, request_text: str, workflow_id: str
) -> None:
    """The same vocabulary starts a workflow as a request and is refused as a question."""
    _assert_question_refused(question, request_text, workflow_id)


def test_no_full_keyword_question_starts_a_workflow() -> None:
    """One sweep over the question and request pairs for guard mutations."""
    for question, request_text, workflow_id in _QUESTION_REQUEST_PAIRS:
        _assert_question_refused(question, request_text, workflow_id)


@pytest.mark.parametrize(
    ("sentence", "form"),
    [
        ("清理低质样本需要审批吗?", "question"),
        ("Is it safe to purge the junk samples?", "question"),
        ("Who approves the cleanup?", "question"),
        ("Do we need sign-off before the metric change?", "question"),
        ("I'd like to know what the cleanup does.", "question"),
        ("帮我看看要不要清理低质样本", "question"),
        ("Can you clean up the low-quality samples?", "request"),
        ("Could you run a dataset health check?", "request"),
        ("能帮我清理一下低质样本吗?", "request"),
        ("可以清理一下低质样本吗?", "request"),
        ("请清理低质样本。", "request"),
        ("Let's weed out the junk files.", "request"),
        ("Do a full health check on this dataset.", "request"),
        ("Clean up the low-quality samples.", "request"),
    ],
)
def test_requests_and_questions_are_told_apart_by_sentence_form(sentence: str, form: str) -> None:
    """Polite requests stay requests; interrogatives and embedded inquiries are questions."""
    assert asks_about_workflow(sentence) is (form == "question")


def test_only_question_sentences_are_blanked() -> None:
    """A request followed by a question keeps the request and its offsets."""
    message = "Clean up the junk samples. How long will it take?"
    kept = requested_text(message)
    assert kept.startswith("Clean up the junk samples.")
    assert kept.strip() == "Clean up the junk samples."
    assert len(kept) == len(message)


@pytest.mark.parametrize(
    ("text", "term"),
    [
        ("we weeded out the junk", "weed out"),
        ("after getting rid of bad files", "get rid of"),
        ("she got rid of them", "get rid of"),
        ("the samples were tidied up", "tidy up"),
        ("swapped the measure", "swap"),
        ("vetting this dataset", "vet"),
        ("it throws away noise", "throw away"),
    ],
)
def test_concept_phrases_match_inflected_verbs(text: str, term: str) -> None:
    """Phrasal and single-word verbs match their regular and common irregular forms."""
    assert inflected_position(text, term) is not None


def test_concepts_are_optional_and_reject_blank_phrasings() -> None:
    """Older contracts load without concepts; declared alternatives must contain text."""
    legacy = WorkflowTriggers(keywords=[["shared"]])
    assert legacy.concepts is None
    assert "concepts" not in legacy.model_dump()
    with pytest.raises(ValidationError):
        WorkflowConcepts(entities=[" "])
    for workflow in list_workflows():
        concepts = workflow.triggers.concepts
        assert concepts is not None
        assert concepts.entities
        assert concepts.actions
        assert workflow.triggers.verification_keywords == []


def test_classifier_candidates_describe_purpose_writes_and_request_vocabulary() -> None:
    """Each candidate states what it does, whether it changes data, and how users ask for it."""
    workflows = list_workflows()
    message = "把低分的条目挑出来处理掉, 再把度量换成标价金额后对比答案。"
    decision = keyword_route(message, workflows)
    prompt = classification_request("fake-script", message, decision, workflows)
    instruction = prompt.messages[0].content
    choices = json.loads(instruction.split("Workflows: ", 1)[1])
    assert {choice["id"] for choice in choices} >= {"low-quality-cleanup", "metric-change"}
    for choice in choices:
        assert choice["changes_data"] is True
        assert choice["steps"]
        assert choice["acts_on"]
        assert choice["request_verbs"]
    assert "who approves it" in instruction
