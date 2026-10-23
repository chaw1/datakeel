# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check the fictional semantic contract and twenty-question benchmark inventory."""

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import BoundaryModel
from datakeel.sample_enterprise.crm import build_crm
from datakeel.sample_enterprise.ecommerce import build_ecommerce
from datakeel.sample_enterprise.erp import build_erp
from datakeel.sample_enterprise.gold import calculate_gold
from datakeel.sample_enterprise.service import build_service


class Question(BoundaryModel):
    """Validate the independently authored ask benchmark input boundary."""

    id: str
    question: str
    expected_status: Literal["answered", "unanswerable", "clarification"]
    metric_id: str | None = None
    gold_key: str | None = None


class Questions(BoundaryModel):
    """Pin the calendar reference used for relative-date benchmark questions."""

    reference_instant: datetime
    questions: list[Question]


def _layer() -> SemanticLayer:
    layers = [
        SemanticLayer.model_validate(yaml.safe_load(path.read_text()))
        for path in sorted(Path("contracts/semantic-layer").glob("*.yaml"))
    ]
    return SemanticLayer(
        metrics=[item for layer in layers for item in layer.metrics],
        dimensions=[item for layer in layers for item in layer.dimensions],
        terms=[item for layer in layers for item in layer.terms],
    )


def test_semantic_contract_inventory_references_generated_columns() -> None:
    """All thirteen metrics and twelve dimensions resolve to real synthetic fields."""
    sources = (build_erp(), build_crm(), build_ecommerce(), build_service())
    columns = {
        f"{source.id}/main/{table.name}/{column}"
        for source in sources
        for table in source.tables
        for column in table.columns
    }
    layer = _layer()
    assert (len(layer.metrics), len(layer.dimensions), len(layer.terms)) == (13, 12, 32)
    assert all(
        metric.measure.column in columns and metric.time.column in columns
        for metric in layer.metrics
    )
    assert all(dimension.column in columns for dimension in layer.dimensions)


def test_three_conflicting_amounts_have_distinct_business_contracts() -> None:
    """Shipment, booked sales, and terminal retail remain three explicit meanings."""
    metrics = [
        metric
        for metric in _layer().metrics
        if metric.id in {"shipment_amount", "sales_amount", "retail_revenue"}
    ]
    assert len({metric.owner for metric in metrics}) == 3
    assert len({metric.measure.column for metric in metrics}) == 3
    assert len({metric.filters[0].value for metric in metrics}) == 3
    assert all(metric.description and metric.caveats for metric in metrics)


def test_questions_have_required_status_mix_and_independent_gold() -> None:
    """Exactly fourteen quantitative questions, four refusals, and two ties are fixed."""
    questions = Questions.model_validate(
        yaml.safe_load(Path("contracts/ask/questions.yaml").read_text())
    )
    gold = calculate_gold((build_erp(), build_crm(), build_ecommerce(), build_service()))
    assert Counter(question.expected_status for question in questions.questions) == {
        "answered": 14,
        "unanswerable": 4,
        "clarification": 2,
    }
    assert questions.reference_instant == gold.reference_instant
    assert {question.gold_key for question in questions.questions if question.gold_key} == set(
        gold.answers
    )
    assert all(question.metric_id for question in questions.questions if question.gold_key)
    prefixes = {"answered": "ok-", "unanswerable": "ua-", "clarification": "cl-"}
    assert all(
        question.id.startswith(prefixes[question.expected_status])
        for question in questions.questions
    )
