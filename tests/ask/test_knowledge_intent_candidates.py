# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify optional model intent candidates never bypass deterministic subject or slot rules."""

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.ask.knowledge_intent_candidates import (
    refine_knowledge_intent,
    verify_candidate_intent,
)
from datakeel.ask.service import ask_data
from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.ask_models import AskRequest
from datakeel.core.errors import ProviderError
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database
from tests.ask.parsing_helpers import registered_question


class _FailingProvider:
    def complete(self, request: ModelRequest) -> ModelResponse:
        msg = "provider unavailable"
        raise ProviderError(msg)


def test_explicit_rules_and_unresolved_subjects_never_call_the_model() -> None:
    """Deterministic direction, explicit ownership, and unknown subjects skip model calls."""
    provider = FakeProvider([])
    for question, subject in (
        ("Who owns inventory?", "inventory"),
        ("出货额谁负责?", "出货额"),
        ("Where does inventory end up?", "inventory"),
        ("周岩负责哪些?", "周岩"),
        ("unregistered_table 谁盯盘?", None),
    ):
        parsed = registered_question(question, subject)
        assert parsed is not None
        assert refine_knowledge_intent(question, parsed, provider) == parsed
    assert provider.requests == []


def test_model_candidates_rescue_unseen_person_metric_and_ambiguous_phrasings() -> None:
    """Verified candidates resolve fallback or ambiguous intents without inventing subjects."""
    person_q = registered_question("inventory 有谁在盯盘?", "inventory")
    assert person_q is not None
    assert person_q.recognition.rule_id == "K3-person-focus"
    provider = FakeProvider([ModelResponse(content='{"intent":"downstream"}')])
    refined_person = refine_knowledge_intent("inventory 有谁在盯盘?", person_q, provider)
    assert refined_person.intent == "downstream"
    assert refined_person.recognition.direction == "downstream"
    assert refined_person.recognition.rule_id == "K18-verified-model-candidate"
    assert provider.requests[0].tools == []

    metric_q = registered_question("inventory_units 会同步到哪些表?", "inventory_units")
    assert metric_q is not None
    assert metric_q.recognition.rule_id == "K5-metric-source"
    refined_metric = refine_knowledge_intent(
        "inventory_units 会同步到哪些表?",
        metric_q,
        FakeProvider([ModelResponse(content='{"intent":"downstream"}')]),
    )
    assert refined_metric.intent == "downstream"
    assert refined_metric.recognition.direction == "downstream"
    assert refined_metric.recognition.rule_id == "K18-verified-model-candidate"

    ambiguous_q = registered_question("出货额有哪些?", "出货额")
    assert ambiguous_q is not None
    assert ambiguous_q.recognition.rule_id == "K8-ambiguous-intent"
    refined_owner = refine_knowledge_intent(
        "出货额有哪些?",
        ambiguous_q,
        FakeProvider([ModelResponse(content='{"intent":"owner"}')]),
    )
    assert refined_owner.intent == "owner"
    assert refined_owner.intent_candidates == ()
    assert not refined_owner.unsupported_phrasing
    assert refined_owner.recognition.direction is None
    assert refined_owner.recognition.rule_id == "K18-verified-model-candidate"


def test_rule_verifier_rejects_invalid_subject_focus_option_and_contradicting_direction() -> None:
    """Incompatible model candidates are discarded so rules retain the final semantic guard."""
    table_focus = registered_question("inventory 的表有哪些", "inventory")
    assert table_focus is not None
    assert table_focus.intent_candidates == ("upstream", "downstream")
    assert verify_candidate_intent(table_focus, "owner") is None
    assert verify_candidate_intent(table_focus, "owned") is None
    assert verify_candidate_intent(table_focus, "none") is None
    assert verify_candidate_intent(table_focus, "upstream") == "upstream"

    location_q = registered_question("inventory 在哪里登记?", "inventory")
    assert location_q is not None
    assert location_q.recognition.rule_id == "K7-location-source"
    assert verify_candidate_intent(location_q, "owner") is None
    assert verify_candidate_intent(location_q, "downstream") == "downstream"

    employment_q = registered_question("Where does priya natarajan work?", "priya natarajan")
    assert employment_q is not None
    assert employment_q.intent_candidates == ("owned", "owner")
    assert verify_candidate_intent(employment_q, "downstream") is None
    assert verify_candidate_intent(employment_q, "owner") == "owner"

    weak_source = registered_question("谁是 inventory 的数据来源?", "inventory")
    assert weak_source is not None
    assert weak_source.recognition.direction == "upstream"
    assert verify_candidate_intent(weak_source, "downstream") is None
    assert verify_candidate_intent(weak_source, "upstream") == "upstream"


@pytest.mark.parametrize(
    "payload",
    [
        "SELECT * FROM orders",
        '{"intent":"downstream","sql":"SELECT 1"}',
        '{"intent":"none"}',
        '{"intent":"owner"}',
    ],
)
def test_malformed_none_and_unchanged_proposals_preserve_deterministic_parse(payload: str) -> None:
    """Malformed JSON, SQL keys, 'none', agreement, and provider errors keep parsed state."""
    parsed = registered_question("出货额该找谁拍板", "出货额")
    assert parsed is not None
    assert parsed.intent == "owner"
    provider = FakeProvider([ModelResponse(content=payload)])
    assert refine_knowledge_intent("出货额该找谁拍板", parsed, provider) == parsed
    assert refine_knowledge_intent("出货额该找谁拍板", parsed, _FailingProvider()) == parsed


def test_ask_data_verifies_injected_provider_candidates_without_overriding_explicit_choice(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Service-level optional provider resolves ambiguous phrasing unless user chose an intent."""
    provider = FakeProvider([ModelResponse(content='{"intent":"owner"}')])
    answer = ask_data(db, AskRequest(question="出货额有哪些?"), provider=provider)
    assert answer.answer_kind == "knowledge"
    assert answer.status == "answered"
    assert answer.knowledge is not None
    assert answer.knowledge.intent == "owner"
    assert answer.recognition is not None
    assert answer.recognition.rule_id == "K18-verified-model-candidate"

    unused = FakeProvider([])
    explicit = ask_data(
        db,
        AskRequest(question="出货额有哪些?", knowledge_intent="upstream"),
        provider=unused,
    )
    assert explicit.knowledge is not None
    assert explicit.knowledge.intent == "upstream"
    assert unused.requests == []
