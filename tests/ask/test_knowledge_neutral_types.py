# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Neutral relations and catalog list commands preserve requested object types."""

import pytest

from datakeel.core.knowledge_models import KnowledgeIntent
from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("有关 inventory 表的视图请列给我看看。", "inventory", "downstream"),
        ("inventory 表关联的指标能列个清单吗?", "inventory", "downstream"),
        ("看板有哪些和 inventory 这张表相关?", "inventory", "downstream"),
        ("和 sales_summary 关联的基础表", "sales_summary", "upstream"),
        ("sales_summary 挂着的指标清单", "sales_summary", "downstream"),
        ("sales_summary 对应的表请给我看看", "sales_summary", "upstream"),
        ("List the views related to inventory.", "inventory", "downstream"),
        ("Reports linked to inventory.", "inventory", "downstream"),
        ("Metrics attached to sales_summary.", "sales_summary", "downstream"),
        ("Base tables associated with sales_summary.", "sales_summary", "upstream"),
        ("Which views belong underneath inventory?", "inventory", "downstream"),
        (
            "For sales_summary, which base tables belong underneath this view?",
            "sales_summary",
            "upstream",
        ),
        ("Show me the dashboards related to inventory.", "inventory", "downstream"),
        ("Show me the tables for sales_summary.", "sales_summary", "upstream"),
        ("inventory 的视图列个清单", "inventory", "downstream"),
        ("sales_summary 的表给我看看", "sales_summary", "upstream"),
        (
            "sales_summary: metrics linked with this view, what are they called?",
            "sales_summary",
            "downstream",
        ),
        (
            "Anything built on inventory — what is it called?",
            "inventory",
            "downstream",
        ),
    ],
)
def test_neutral_typed_request_uses_catalog_hierarchy(
    question: str, subject: str, intent: KnowledgeIntent
) -> None:
    """Route neutral cross-layer relationships to knowledge with the correct subject."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert not parsed.unsupported_phrasing
    assert parsed.candidates[0].name == subject


@pytest.mark.parametrize(
    "question",
    [
        "inventory 关联的表列个清单",
        "Tables attached to inventory.",
        "Show me tables related to inventory.",
        "Which tables belong underneath inventory?",
    ],
)
def test_neutral_same_layer_keeps_intent_clarification(question: str) -> None:
    """A neutral relation alone cannot invent direction between peers."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == "related"
    assert parsed.intent_candidates == ("upstream", "downstream")
