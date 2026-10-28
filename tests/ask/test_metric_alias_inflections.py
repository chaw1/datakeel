# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit common English alias inflections resolve through the full numeric service."""

from datetime import UTC, datetime

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import SemanticLayer
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)

ALIAS_PAIRS = (
    ("shipment_amount", "shipping value", "shipping values"),
    ("shipment_amount", "dispatched value", "dispatched values"),
    ("sales_amount", "invoiced sale", "invoiced sales"),
    ("sales_amount", "sales revenue", "sales revenues"),
    ("retail_revenue", "retail sale", "retail sales"),
    ("retail_revenue", "consumer spending", "consumer spending"),
    ("order_count", "number of order", "number of orders"),
    ("order_count", "completed order", "completed orders"),
    ("refund_amount", "refund value", "refund values"),
    ("refund_amount", "refunded total", "refunded totals"),
    ("inventory_units", "stock quantity", "stock quantities"),
    ("inventory_units", "available stock", "available stocks"),
    ("customer_count", "number of customer", "number of customers"),
    ("customer_count", "registered customer", "registered customers"),
    ("ticket_count", "support ticket count", "support ticket counts"),
    ("ticket_count", "number of service ticket", "number of service tickets"),
    ("repair_cost", "repair expense", "repair expenses"),
    ("repair_cost", "maintenance labor cost", "maintenance labor costs"),
    ("payment_amount", "collected payment", "collected payments"),
    ("payment_amount", "payment value", "payment values"),
    ("sales_units", "sales volume", "sales volumes"),
    ("sales_units", "invoiced unit", "invoiced units"),
    ("shipment_units", "shipped quantity", "shipped quantities"),
    ("shipment_units", "dispatched unit", "dispatched units"),
    ("retail_units", "retail volume", "retail volumes"),
    ("retail_units", "retail item quantity", "retail item quantities"),
)


def test_shipped_english_names_and_aliases_have_unique_metric_identities(
    layer: SemanticLayer,
) -> None:
    """The example English vocabulary stays unambiguous even as inflection pairs are registered."""
    identities: dict[str, set[str]] = {}
    for metric in layer.metrics:
        names = [*metric.synonyms, *([metric.english_name] if metric.english_name else [])]
        for name in names:
            if name.isascii():
                identities.setdefault(name.casefold(), set()).add(metric.id)
    assert all(len(targets) == 1 for targets in identities.values())


@pytest.mark.parametrize(("metric_id", "singular", "plural"), ALIAS_PAIRS)
def test_registered_alias_inflections_equal_chinese_without_changing_identifier_rules(
    db: Database,
    enterprise_sample: EnterpriseSample,
    layer: SemanticLayer,
    metric_id: str,
    singular: str,
    plural: str,
) -> None:
    """Common count-noun variants are registered vocabulary, including ordinary quantity plurals."""
    metric = next(item for item in layer.metrics if item.id == metric_id)
    assert len(metric.synonyms) == len(set(metric.synonyms))
    assert singular in metric.synonyms
    assert plural in metric.synonyms
    chinese = ask_data(db, AskRequest(question=metric.name, reference_instant=REFERENCE))
    assert chinese.status == "answered"
    for phrase in dict.fromkeys((singular, plural)):
        answer = ask_data(
            db, AskRequest(question=f"Show me the {phrase.swapcase()}", reference_instant=REFERENCE)
        )
        assert answer.answer_kind == "metric", phrase
        assert answer.status == "answered", phrase
        assert answer.metric_card is not None
        assert answer.metric_card.definition.id == metric_id
        assert answer.result == chinese.result
