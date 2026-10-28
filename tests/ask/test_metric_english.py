# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""English metric registration and restricted identifier inflection stay deterministic."""

from datetime import UTC, datetime

import pytest

from datakeel.ask.matching import metric_matches
from datakeel.ask.parser import parse_question
from datakeel.ask.resolution import resolve_metric
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import MetricCard, MetricDefinition, SemanticLayer
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database
from datakeel.storage.metric_store import install_layer

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)
_METRIC_IDS = (
    "shipment_amount",
    "sales_amount",
    "retail_revenue",
    "order_count",
    "refund_amount",
    "inventory_units",
    "customer_count",
    "ticket_count",
    "repair_cost",
    "payment_amount",
    "sales_units",
    "shipment_units",
    "retail_units",
)


def _identifier_layer(layer: SemanticLayer) -> SemanticLayer:
    return SemanticLayer(
        metrics=[
            metric.model_copy(update={"english_name": None, "synonyms": []})
            for metric in layer.metrics
        ]
    )


def _resolve(question: str, layer: SemanticLayer) -> tuple[str, tuple[str, ...]]:
    resolution = resolve_metric(
        parse_question(AskRequest(question=question), layer),
        [MetricCard(definition=metric) for metric in layer.metrics],
    )
    return resolution.status, tuple(card.definition.id for card in resolution.candidates)


@pytest.mark.parametrize(
    ("phrase", "metric_id"),
    [
        ("REFUND AMOUNT", "refund_amount"),
        ("refund-amount", "refund_amount"),
        ("refund_amount", "refund_amount"),
        ("Refund Amounts", "refund_amount"),
        ("refund\tamounts", "refund_amount"),
        ("REFUNDS_AMOUNTS", "refund_amount"),
        ("order-counts", "order_count"),
        ("orders counts", "order_count"),
        ("customer counts", "customer_count"),
        ("repair costs", "repair_cost"),
        ("retail revenues", "retail_revenue"),
        ("Sale Unit", "sales_units"),
        ("inventory unit", "inventory_units"),
        ("shipments units", "shipment_units"),
        ("ticket counts", "ticket_count"),
        ("payment-amounts", "payment_amount"),
        ("retail_units", "retail_units"),
        ("Sales Amounts", "sales_amount"),
    ],
)
def test_id_forms_resolve_without_registered_english_aliases(
    layer: SemanticLayer, phrase: str, metric_id: str
) -> None:
    """Case, separators and regular plural forms retain exact original evidence spans."""
    isolated = _identifier_layer(layer)
    question = f"Show the {phrase}?"
    matches = metric_matches(question, isolated)
    assert _resolve(question, isolated) == ("resolved", (metric_id,))
    assert any(match.match_kind == "normalized" for match in matches)
    assert all(question[item.start : item.end] == item.text for item in matches)


@pytest.mark.parametrize(
    "question",
    [
        "refund rate",
        "refund_amounter",
        "refunding amount",
        "ordercounter",
        "order.count",
        "repair costing",
        "consumer satisfaction",
        "refund_amount_v2",
        "order countess",
        "inventory unities",
        "preorder_count",
    ],
)
def test_id_normalization_does_not_expand_into_unregistered_meanings(
    layer: SemanticLayer, question: str
) -> None:
    """Identifier matching is whole-token morphology, never fuzzy or semantic expansion."""
    assert metric_matches(question, _identifier_layer(layer)) == ()


@pytest.mark.parametrize(
    ("identifier", "phrase"),
    [
        ("process_count", "Processes Counts"),
        ("tax_total", "Taxes Totals"),
        ("status_count", "Statuses Counts"),
        ("business_count", "Businesses Counts"),
    ],
)
def test_id_regular_es_plurals_preserve_metric_identity(
    layer: SemanticLayer, identifier: str, phrase: str
) -> None:
    """Words ending in s or x accept their regular es plural without extra stemming."""
    metric = layer.metrics[0].model_copy(
        update={"id": identifier, "name": "示例指标", "english_name": None, "synonyms": []}
    )
    assert _resolve(phrase, SemanticLayer(metrics=[metric])) == ("resolved", (identifier,))


def test_id_normalization_collision_lists_every_candidate(layer: SemanticLayer) -> None:
    """Two registered identities collapsing to one id word form must remain ambiguous."""
    first = next(item for item in _identifier_layer(layer).metrics if item.id == "refund_amount")
    second = first.model_copy(update={"id": "refund_amounts", "name": "其他退款额"})
    assert _resolve("Refund Amounts", SemanticLayer(metrics=[first, second])) == (
        "clarification",
        ("refund_amount", "refund_amounts"),
    )


def test_registered_english_name_and_synonym_collision_requires_clarification(
    layer: SemanticLayer,
) -> None:
    """An explicit English name cannot silently win over another metric's same alias."""
    first = (
        _identifier_layer(layer)
        .metrics[0]
        .model_copy(update={"id": "first", "english_name": "Refund Value"})
    )
    second = first.model_copy(
        update={
            "id": "second",
            "name": "其他指标",
            "english_name": None,
            "synonyms": ["Refund Value"],
        }
    )
    assert _resolve("Refund Value", SemanticLayer(metrics=[first, second])) == (
        "clarification",
        ("first", "second"),
    )


@pytest.mark.parametrize("registered_field", ["english_name", "synonyms"])
def test_registered_english_names_and_aliases_outrank_normalized_ids(
    layer: SemanticLayer, registered_field: str
) -> None:
    """Explicitly registered vocabulary wins before the fallback identifier layer."""
    first = (
        _identifier_layer(layer)
        .metrics[0]
        .model_copy(
            update={
                "id": "registered_metric",
                registered_field: "Refund Amount"
                if registered_field == "english_name"
                else ["Refund Amount"],
            }
        )
    )
    second = next(item for item in _identifier_layer(layer).metrics if item.id == "refund_amount")
    assert _resolve("Refund Amount", SemanticLayer(metrics=[first, second])) == (
        "resolved",
        ("registered_metric",),
    )


def test_normalized_id_outranks_conservative_name_prefix(layer: SemanticLayer) -> None:
    """A truncated registered name cannot override an entire normalized identifier."""
    first = next(item for item in _identifier_layer(layer).metrics if item.id == "refund_amount")
    second = first.model_copy(update={"id": "other_metric", "name": "Refund Amount Extended"})
    assert _resolve("Refund Amount", SemanticLayer(metrics=[first, second])) == (
        "resolved",
        ("refund_amount",),
    )


def test_normalized_identifiers_keep_ascii_word_boundaries(layer: SemanticLayer) -> None:
    """A longer programmatic identifier cannot impersonate one registered metric id."""
    isolated = _identifier_layer(layer)
    for question in ("refund_amount_v2", "preorder_count", "repair_costing"):
        assert metric_matches(question, isolated) == ()


@pytest.mark.parametrize("identifier", ["_", "refund_", "s", "refund2_amount"])
def test_unusual_ids_never_create_empty_match_evidence(
    layer: SemanticLayer, identifier: str
) -> None:
    """Malformed separators and short or numeric tokens cannot turn into empty patterns."""
    metric = layer.metrics[0].model_copy(
        update={"id": identifier, "english_name": None, "synonyms": []}
    )
    assert metric_matches("Show an unrelated value", SemanticLayer(metrics=[metric])) == ()


@pytest.mark.parametrize("metric_id", _METRIC_IDS)
def test_english_names_synonyms_and_id_forms_equal_chinese_numeric_answers(
    db: Database,
    enterprise_sample: EnterpriseSample,
    layer: SemanticLayer,
    metric_id: str,
) -> None:
    """Every shipped metric yields the same read-only result through each English entry path."""
    metric = next(item for item in layer.metrics if item.id == metric_id)
    english_synonyms = [name for name in metric.synonyms if name.isascii()]
    assert metric.english_name
    assert len(english_synonyms) >= 2
    chinese = ask_data(db, AskRequest(question=metric.name, reference_instant=REFERENCE))
    assert chinese.status == "answered"
    head, _, tail = metric.id.rpartition("_")
    inflected = tail[:-1] if tail.endswith("s") else tail + "s"
    for phrase in (
        metric.english_name,
        *english_synonyms,
        metric.id.upper().replace("_", "-"),
        f"{head} {inflected}".title(),
    ):
        answer = ask_data(
            db, AskRequest(question=f"Show me the {phrase}", reference_instant=REFERENCE)
        )
        assert answer.status == "answered", phrase
        assert answer.answer_kind == "metric", phrase
        assert answer.metric_card is not None
        assert answer.metric_card.definition.id == metric_id
        assert answer.result == chinese.result, phrase


@pytest.mark.parametrize(
    "question",
    [
        "Who owns the refund amount?",
        "Who is responsible for Repair Costs?",
        "Which team owns the order count?",
        "退款金额的负责人是谁?",
        "谁是 Refund Amount 的负责人?",
        "哪个团队负责 repair_cost?",
    ],
)
def test_english_metric_mentions_with_person_focus_never_return_numbers(
    db: Database, enterprise_sample: EnterpriseSample, question: str
) -> None:
    """Broader lexical recall preserves the knowledge-before-numeric ownership guard."""
    answer = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
    assert answer.answer_kind == "knowledge"
    assert answer.result is None
    assert answer.sql is None


def test_ambiguous_id_forms_never_execute_numeric_query(
    db: Database, enterprise_sample: EnterpriseSample, layer: SemanticLayer
) -> None:
    """The full service returns stable candidates and no query for normalized collisions."""
    metric = next(item for item in _identifier_layer(layer).metrics if item.id == "refund_amount")
    second = metric.model_copy(update={"id": "refund_amounts", "name": "其他退款额"})
    install_layer(db, SemanticLayer(metrics=[metric, second]))
    answer = ask_data(db, AskRequest(question="Refund Amounts", reference_instant=REFERENCE))
    assert answer.status == "clarification"
    assert {card.definition.id for card in answer.candidates} == {"refund_amount", "refund_amounts"}
    assert answer.sql is None
    assert answer.result is None


def test_normalized_english_owner_focus_and_metric_value_use_separate_routes(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Inflected metric identifiers retain both numeric recall and the person safety guard."""
    numeric = ask_data(db, AskRequest(question="Show REFUNDS-AMOUNTS", reference_instant=REFERENCE))
    assert numeric.status == "answered"
    assert numeric.metric_card is not None
    assert numeric.metric_card.definition.id == "refund_amount"
    owner = ask_data(
        db, AskRequest(question="Who owns REFUNDS-AMOUNTS?", reference_instant=REFERENCE)
    )
    assert owner.answer_kind == "knowledge"
    assert owner.status == "answered"
    assert owner.sql is None
    assert owner.result is None


def test_legacy_metric_definition_omits_optional_english_name(layer: SemanticLayer) -> None:
    """Existing contract files keep loading without filling the additive English label."""
    document = layer.metrics[0].model_dump(exclude={"english_name"})
    assert MetricDefinition.model_validate(document).english_name is None
