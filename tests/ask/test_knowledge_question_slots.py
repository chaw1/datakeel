# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Source/result minimal pairs keep interrogatives independent of topic word order."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("What is derived from the inventory table?", "inventory", "downstream"),
        ("What is inventory derived from?", "inventory", "upstream"),
        ("Which reports are built from the inventory table?", "inventory", "downstream"),
        ("Which tables is inventory built from?", "inventory", "upstream"),
        ("inventory: what is made from it?", "inventory", "downstream"),
        ("inventory: what is it made from?", "inventory", "upstream"),
        (
            "inventory is the foundation: which reports are derived from it?",
            "inventory",
            "downstream",
        ),
        ("For inventory, which reports are derived from that table?", "inventory", "downstream"),
        ("inventory — which reports use this table?", "inventory", "downstream"),
        ("inventory — which tables does this table use?", "inventory", "upstream"),
        ("sales_summary: who consumes the output of this view?", "sales_summary", "downstream"),
        ("sales_summary: who does this view depend on?", "sales_summary", "upstream"),
        ("inventory\uff1a谁还在依赖这张表而受影响\uff1f", "inventory", "downstream"),
        ("inventory\uff1a这张表还在依赖哪些表\uff1f", "inventory", "upstream"),
        ("inventory\uff1a哪些产物把它当作基础\uff1f", "inventory", "downstream"),
        ("哪些产物把这张表当作基础\uff1ainventory\uff1f", "inventory", "downstream"),
        ("inventory 被当成依据之后\uff0c生成了哪些东西\uff1f", "inventory", "downstream"),
        ("inventory 是在哪张表的基础上做的\uff1f", "inventory", "upstream"),
        ("inventory 是以哪些表的基础上加工的\uff1f", "inventory", "upstream"),
        ("inventory 基于哪张表\uff1f", "inventory", "upstream"),
        ("inventory_units: what table supplies its raw records?", "inventory_units", "upstream"),
        ("retention: which tables supply its raw records?", "retention", "upstream"),
        ("Can you list the assets whose input is inventory?", "inventory", "downstream"),
        ("Can you list the assets whose output is inventory?", "inventory", "upstream"),
        ("Anything built on inventory — what is it called?", "inventory", "downstream"),
    ],
)
def test_question_slots_resolve_topic_and_fronted_arguments(
    question: str, subject: str, intent: str
) -> None:
    """The queried slot survives pronouns, omitted objects and source/result inversion."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert len(parsed.candidates) == 1
    assert parsed.candidates[0].name == subject
    assert all("§" not in words for words in parsed.recognition.direction_text)


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What would lose its data feed if we retired inventory?", "downstream"),
        ("If we dropped inventory, which reports would break?", "downstream"),
        ("If we removed inventory, what would stop refreshing?", "downstream"),
        ("inventory 一旦断供\uff0c哪些会受牵连\uff1f", "downstream"),
        ("如果 inventory 停掉\uff0c哪些看板会坏\uff1f", "downstream"),
        ("要是 inventory 没了\uff0c谁还在依赖它而受牵连\uff1f", "downstream"),
        ("inventory\uff0c若停供\uff0c哪些报告受影响\uff1f", "downstream"),
        ("If a source were removed, which tables would inventory depend on?", "upstream"),
        ("如果哪些输入没了\uff0cinventory 会坏\uff1f", "upstream"),
        ("Who maintains inventory if we retire its source?", "owner"),
        ("inventory 一旦断供\uff0c谁负责恢复\uff1f", "owner"),
        ("Where does inventory flow next?", "downstream"),
        ("Where does inventory flow from?", "upstream"),
        ("Where does inventory flow in from?", "upstream"),
        ("Where does inventory flow out of?", "upstream"),
        ("Where does inventory go next?", "downstream"),
        ("inventory 接下来流向哪里\uff1f", "downstream"),
        ("inventory 的下一站是哪里\uff1f", "downstream"),
        ("inventory 不能用了会影响谁\uff1f", "downstream"),
    ],
)
def test_counterfactual_and_flow_slots_keep_the_requested_side(question: str, intent: str) -> None:
    """Lost sources and flow destinations stay distinct from missing inputs and owners."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("sales_summary — how many metrics depend on this view?", "downstream"),
        ("sales_summary: how many metrics does it depend on?", "upstream"),
        ("sales_summary\uff1a多少个指标会使用这个视图\uff1f", "downstream"),
        ("sales_summary\uff1a这个视图使用多少个指标\uff1f", "upstream"),
    ],
)
def test_counted_dependency_uses_the_same_question_slots(question: str, intent: str) -> None:
    """Counting catalog dependants preserves the typed knowledge count request."""
    parsed = registered_question(question, "sales_summary")
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.count_focus is not None
    assert parsed.count_focus.target_kind == "metric"
    assert parsed.count_focus.counted


def test_topic_pronoun_direction_cannot_follow_the_topic_position() -> None:
    """A mutation reversing the queried result slot must fail this minimal pair."""
    for question, intent in (
        ("sales_summary — which metrics depend on this view?", "downstream"),
        ("sales_summary — which metrics does this view depend on?", "upstream"),
    ):
        parsed = registered_question(question, "sales_summary")
        assert parsed is not None
        assert parsed.intent == intent
        assert parsed.recognition.rule_id == "K15-question-slot"
