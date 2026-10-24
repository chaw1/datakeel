# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep destination complements and display consumers directed by sentence roles."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "direction"),
    [
        ("哪些数据流入 orders\uff1f", "orders", "upstream"),
        ("orders 流入哪些表\uff1f", "orders", "downstream"),
        ("What is fed into inventory_units?", "inventory_units", "upstream"),
        ("inventory_units is fed into which dashboards?", "inventory_units", "downstream"),
        ("给 sales_summary 提供数据的表都有哪些\uff1f", "sales_summary", "upstream"),
        ("有哪些看板会显示库存量\uff1f", "库存量", "downstream"),
        ("inventory_units appears on which dashboards?", "inventory_units", "downstream"),
        ("inventory_units comes from which dashboards?", "inventory_units", "upstream"),
        ("库存量来自哪些看板\uff1f", "库存量", "upstream"),
        ("给 sales_summary 供数的表有哪些\uff1f", "sales_summary", "upstream"),
    ],
)
def test_flow_complement_assigns_input_and_result_roles(
    question: str, subject: str, direction: str
) -> None:
    """Infer the same relation for input and recipient placements."""
    answer = registered_question(question, subject)
    assert answer is not None
    assert answer.intent == direction
    assert not answer.intent_candidates
    assert not answer.unsupported_phrasing


@pytest.mark.parametrize("question", ["显示库存量的数值", "What is the value of inventory_units?"])
def test_display_value_commands_keep_metric_route(question: str) -> None:
    """An explicit displayed value remains a numerical request."""
    subject = "inventory_units" if "inventory_units" in question else "库存量"
    assert registered_question(question, subject) is None
