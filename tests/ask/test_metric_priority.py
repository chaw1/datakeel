# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A complete registered metric name outranks the generic words it contains."""

from datetime import UTC, datetime

import pytest

from datakeel.ask import service
from datakeel.ask.parser import parse_question
from datakeel.ask.resolution import resolve_metric
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import CompiledQuery, MetricCard, QueryResult, SemanticLayer
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)
_GENERIC = ("amount", "count", "units", "cost", "金额", "数量")


def _resolve(question: str, layer: SemanticLayer) -> tuple[str, tuple[str, ...]]:
    resolution = resolve_metric(
        parse_question(AskRequest(question=question), layer),
        [MetricCard(definition=metric) for metric in layer.metrics],
    )
    return resolution.status, tuple(card.definition.id for card in resolution.candidates)


def test_every_registered_name_with_a_generic_head_resolves_to_itself(
    layer: SemanticLayer,
) -> None:
    """Names such as refund amount or shipment units are not split into a generic conflict."""
    checked = 0
    for metric in layer.metrics:
        for name in [metric.name, metric.english_name or "", *metric.synonyms]:
            if name and any(word in name.casefold() for word in _GENERIC):
                assert _resolve(f"What is the {name}?", layer) == ("resolved", (metric.id,)), name
                checked += 1
    assert checked >= 20


@pytest.mark.parametrize(
    ("question", "metric_id"),
    [
        ("How many support tickets were opened last quarter?", "ticket_count"),
        ("service ticket volume in March 2026", "ticket_count"),
        ("booked sales last month", "sales_amount"),
        ("stock on hand as of September 2026", "inventory_units"),
        ("units shipped in Q2 2026", "shipment_units"),
        ("cash collected last quarter", "payment_amount"),
        ("customer base in East China", "customer_count"),
        ("maintenance cost by region", "repair_cost"),
        ("retail turnover in Q2 2026", "retail_revenue"),
        ("shipment value last month", "shipment_amount"),
        ("amount refunded in March 2026", "refund_amount"),
        ("order volume last quarter", "order_count"),
    ],
)
def test_common_english_business_names_resolve_by_domain(
    layer: SemanticLayer, question: str, metric_id: str
) -> None:
    """Each domain carries the English names analysts commonly use, not only test phrasings."""
    assert _resolve(question, layer) == ("resolved", (metric_id,))


@pytest.mark.parametrize(
    "question",
    [
        "what is the total amount?",
        "how many units",
        "How many units did we sell last quarter?",
        "total cost last month",
        "9月的金额",
        "上个季度的数量是多少",
    ],
)
def test_generic_words_alone_still_require_clarification_and_never_execute(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
) -> None:
    """A generic head with no registered name lists candidates and runs no query."""
    assert enterprise_sample.sources
    executed: list[CompiledQuery] = []

    def record(_url: str, query: CompiledQuery) -> QueryResult:
        executed.append(query)
        return QueryResult(columns=["value"], rows=[[1]])

    monkeypatch.setattr(service, "execute_query", record)
    answer = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
    assert answer.status == "clarification", (question, answer.message)
    assert len(answer.candidates) > 1
    assert answer.result is None
    assert executed == []


def test_nested_registered_name_inside_a_longer_one_is_not_a_conflict(
    layer: SemanticLayer,
) -> None:
    """``retail revenue`` contains ``revenue``-like heads but resolves to one metric."""
    assert _resolve("retail sales amount last quarter", layer) == ("resolved", ("retail_revenue",))
    assert _resolve("retail units sold in East China", layer)[0] == "resolved"
