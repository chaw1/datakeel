# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Separate aggregate and catalog question heads from incidental grouping/filter nouns."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent", "count_target"),
    [
        ("What is the total inventory_units for each team?", "inventory_units", None, None),
        ("Which team owns the total inventory_units?", "inventory_units", "owner", None),
        ("What is the total inventory_units by person?", "inventory_units", None, None),
        ("Who owns the total inventory_units?", "inventory_units", "owner", None),
        (
            "What is the total inventory_units for people who manage stores?",
            "inventory_units",
            None,
            None,
        ),
        ("Who manages the total inventory_units?", "inventory_units", "owner", None),
        ("Show the total inventory_units for the team", "inventory_units", None, None),
        ("Show the owner of the total inventory_units", "inventory_units", "owner", None),
        ("inventory_units 按团队统计的总额是什么", "inventory_units", None, None),
        ("inventory_units 的总额由哪个团队负责", "inventory_units", "owner", None),
        ("按人员查看 inventory_units 的总额", "inventory_units", None, None),
        ("inventory_units 总额的负责人是谁", "inventory_units", "owner", None),
        (
            "What is the total inventory_units from stores where teams work?",
            "inventory_units",
            None,
            None,
        ),
        ("Where does the total inventory_units come from?", "inventory_units", "upstream", None),
        (
            "What is the total inventory_units for teams whose stores are active?",
            "inventory_units",
            None,
            None,
        ),
        ("Whose metric is the total inventory_units?", "inventory_units", "owner", None),
        ("What is the total inventory_units for owners?", "inventory_units", None, None),
        ("Who is the owner of the total inventory_units?", "inventory_units", "owner", None),
        (
            "What are the total inventory_units for tables in this report?",
            "inventory_units",
            None,
            None,
        ),
        ("What tables feed the total inventory_units?", "inventory_units", "upstream", None),
        ("What is the total inventory_units on reports?", "inventory_units", None, None),
        ("What reports use the total inventory_units?", "inventory_units", "downstream", None),
        ("Show inventory_units for people who manage stores", "inventory_units", None, None),
        ("Show who manages inventory_units", "inventory_units", "owner", None),
        ("Show inventory_units for teams where stores are active", "inventory_units", None, None),
        ("Show where inventory_units comes from", "inventory_units", "upstream", None),
        ("Show inventory_units where teams are active", "inventory_units", None, None),
        ("Where does inventory_units come from?", "inventory_units", "upstream", None),
        ("Show inventory_units by people who own stores", "inventory_units", None, None),
        ("Who owns inventory_units for stores?", "inventory_units", "owner", None),
        ("Show inventory_units per team where stores are active", "inventory_units", None, None),
        ("Which teams use inventory_units for stores?", "inventory_units", "downstream", None),
        ("统计各团队负责的 inventory_units 总额", "inventory_units", None, None),
        ("inventory_units 的总额来源是什么", "inventory_units", "upstream", None),
        ("What is the highest inventory_units for each team?", "inventory_units", None, None),
        ("What is the formula for the total inventory_units?", "inventory_units", "upstream", None),
        ("How much inventory_units comes from each team?", "inventory_units", None, None),
        ("What is the source of the total inventory_units?", "inventory_units", "upstream", None),
        (
            "What is the value of inventory_units for people who own stores?",
            "inventory_units",
            None,
            None,
        ),
        ("Who owns the value of inventory_units?", "inventory_units", "owner", None),
        ("inventory_units for how many teams?", "inventory_units", "owner", "team"),
        ("inventory_units by how many tables?", "inventory_units", "upstream", "table"),
        ("inventory_units by what tables?", "inventory_units", "upstream", None),
        ("inventory_units for whose team?", "inventory_units", "owner", None),
        ("inventory_units for which team?", "inventory_units", "owner", None),
        ("For which team is inventory_units?", "inventory_units", "owner", None),
        ("inventory_units by which tables?", "inventory_units", "upstream", None),
        (
            "Show inventory_units by which tables it is computed?",
            "inventory_units",
            "upstream",
            None,
        ),
        (
            "What is the total number of metrics that use inventory?",
            "inventory",
            "downstream",
            "metric",
        ),
        ("What is the total number of orders for each team?", "inventory_units", None, None),
        (
            "What is the total number of people who maintain inventory?",
            "inventory",
            "owner",
            "person",
        ),
        (
            "What is the total inventory_units for people who maintain tables?",
            "inventory_units",
            None,
            None,
        ),
        (
            "What is the total number of tables that feed inventory_units?",
            "inventory_units",
            "upstream",
            "table",
        ),
        (
            "What is the total inventory_units for tables that feed reports?",
            "inventory_units",
            None,
            None,
        ),
        ("inventory 下游的指标总共有多少个", "inventory", "downstream", "metric"),
        ("inventory_units 团队负责的总额是多少", "inventory_units", None, None),
        ("Show where the total inventory_units comes from", "inventory_units", "upstream", None),
        ("Show inventory_units where total = 10", "inventory_units", None, None),
        ("Show inventory_units where it comes from", "inventory_units", "upstream", None),
        ("Show inventory_units where owner = 'Morgan'", "inventory_units", None, None),
        ("Show inventory_units for teams who own source tables", "inventory_units", None, None),
        ("Show the teams who own inventory_units", "inventory_units", "owner", None),
        (
            "Which tables feed the total inventory_units for teams?",
            "inventory_units",
            "upstream",
            None,
        ),
        ("What is the highest total inventory_units for teams?", "inventory_units", None, None),
    ],
)
def test_numeric_heads_preserve_relation_and_count_boundaries(
    question: str, subject: str, intent: str | None, count_target: str | None
) -> None:
    """A value or relation head wins over nouns inside its grouping and filtering clauses."""
    parsed = registered_question(question, subject)
    if intent is None:
        assert parsed is None
        return
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    if count_target is not None:
        assert parsed.count_focus is not None
        assert parsed.count_focus.counted
        assert parsed.count_focus.target_kind == count_target
