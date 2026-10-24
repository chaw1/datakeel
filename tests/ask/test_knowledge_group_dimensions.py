# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dimension positions stay numerical while real ownership and source questions remain safe."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    "question",
    [
        "Break down inventory_units by source channel.",
        "Break inventory_units down by source channel.",
        "Please break inventory_units down by downstream channel.",
        "Give each upstream supplier's inventory_units.",
        "List inventory_units by owner.",
        "Display inventory_units grouped by source.",
        "Group inventory_units by downstream channels.",
        "For each owner, give me inventory_units.",
        "For each upstream supplier, give me inventory_units.",
        "Give me inventory_units per owner.",
        "Each owner's inventory_units",
        "Each downstream channel\u2019s inventory_units",
        "Show each source's inventory_units.",
        "inventory_units group by owner",
        "Break down inventory_units by upstream provider.",
        "库存量按负责人分组。",
        "库存量分来源展示。",
        "分负责人查看库存量。",
        "每个负责人的库存量。",
        "按来源分组\uff0c给我库存量。",
        "按下游渠道展示库存量。",
        "按上游供应商查看库存量。",
    ],
)
def test_group_dimensions_do_not_become_knowledge_focus(question: str) -> None:
    """A nominal dimension is not an owner, input or consumer being requested."""
    subject = "库存量" if "库存量" in question else "inventory_units"
    assert registered_question(question, subject) is None


@pytest.mark.parametrize(
    "question",
    [
        "What is this month's inventory_units?",
        "What was last quarter\u2019s inventory_units?",
        "What is this year's inventory_units?",
        "What is inventory_units this week?",
        "本月的库存量是多少\uff1f",
    ],
)
def test_timed_metric_head_ignores_time_possessive(question: str) -> None:
    """A date modifies the requested scalar without creating a knowledge focus."""
    subject = "库存量" if "库存量" in question else "inventory_units"
    assert registered_question(question, subject) is None


@pytest.mark.parametrize(
    "question",
    [
        "Who owns inventory_units by source?",
        "Who uses inventory_units per upstream supplier?",
        "Who owns this month's inventory_units?",
        "Which person owns inventory_units by downstream channel?",
        "库存量分来源之后由谁负责\uff1f",
        "按负责人汇总的库存量归哪位维护\uff1f",
        "每个区域的库存量是谁负责的\uff1f",
        "Who owns each source's inventory_units?",
    ],
)
def test_group_dimension_preserves_person_question_without_numeric_clues(question: str) -> None:
    """A person interrogative outside the nominal dimension cannot enter metric execution."""
    subject = "库存量" if "库存量" in question else "inventory_units"
    assert registered_question(question, subject) is not None


@pytest.mark.parametrize(
    "question",
    [
        "What is the source of this month's inventory_units?",
        "inventory_units 分管团队",
        "What is the formula of inventory_units by source?",
        "Which tables feed inventory_units per downstream channel?",
        "What is the owner of inventory_units for each upstream supplier?",
        "每个区域的库存量来自哪些表\uff1f",
        "库存量分来源统计后依赖哪些表\uff1f",
        "库存量按上游供应商汇总的口径归哪个团队\uff1f",
    ],
)
def test_group_dimension_preserves_explicit_knowledge_focus(question: str) -> None:
    """Removing nominal group dimensions must preserve the main relation question."""
    subject = "库存量" if "库存量" in question else "inventory_units"
    assert registered_question(question, subject) is not None


def test_group_dimension_words_cannot_redirect_numeric_requests() -> None:
    """Exercise dimension masking as one mutation witness across multiple scalar forms."""
    questions = (
        "Group inventory_units by downstream channels.",
        "Break inventory_units down by source channel.",
        "For each owner, give me inventory_units.",
        "Each upstream supplier's inventory_units",
    )
    for question in questions:
        assert registered_question(question, "inventory_units") is None
