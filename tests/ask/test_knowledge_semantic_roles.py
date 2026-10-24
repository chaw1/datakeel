# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Development minimal pairs bind focus and dependency roles to the main question."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent", "focus"),
    [
        ("inventory 关联的用于展示指标的报表有哪些", "inventory", "downstream", "table"),
        ("inventory 关联的在报表中展示的指标有哪些", "inventory", "downstream", "metric"),
        ("inventory 由哪些维护报表的团队负责", "inventory", "owner", "person"),
        ("inventory 供哪些团队维护的报表使用", "inventory", "downstream", "table"),
        (
            "Which teams responsible for the reports maintain inventory?",
            "inventory",
            "owner",
            "person",
        ),
        (
            "Which reports maintained by the teams use inventory?",
            "inventory",
            "downstream",
            "table",
        ),
        (
            "What metrics in the reports depend on sales_summary?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        ("What reports with metrics depend on inventory?", "inventory", "downstream", "table"),
        ("inventory 供哪些团队维护的指标使用", "inventory", "downstream", "metric"),
        ("哪些团队使用 inventory 的数据", "inventory", "downstream", "person"),
        ("哪些表使用 inventory 的数据", "inventory", "downstream", "table"),
        ("哪些团队维护 inventory 的报表", "inventory", "owner", "person"),
        ("inventory 由哪些报表维护团队负责", "inventory", "owner", "person"),
    ],
)
def test_development_nominal_attributes_keep_the_requested_head(
    question: str, subject: str, intent: str, focus: str
) -> None:
    """A requested relative noun wins without crossing a hidden registered subject."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert bool(parsed.intent_candidates) == (intent == "related")


@pytest.mark.parametrize(
    ("question", "subject", "intent", "focus"),
    [
        ("inventory 让哪些表使用", "inventory", "downstream", "table"),
        ("inventory 使用哪些表", "inventory", "upstream", "table"),
        ("inventory 给哪些表使用", "inventory", "downstream", "table"),
        ("inventory 被哪些表使用", "inventory", "downstream", "table"),
        ("哪些表给 inventory 使用", "inventory", "upstream", "table"),
        ("哪些表让 inventory 使用", "inventory", "upstream", "table"),
        ("给 inventory 使用的表有哪些", "inventory", "upstream", "table"),
        ("inventory 让哪些指标读取", "inventory", "downstream", "metric"),
        ("哪些指标让 inventory 读取", "inventory", "upstream", "metric"),
    ],
)
def test_development_recipient_usage_preserves_consumer_and_resource_roles(
    question: str, subject: str, intent: str, focus: str
) -> None:
    """Causative and recipient frames distinguish the consumed asset from its consumer."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert bool(parsed.intent_candidates) == (intent == "related")


@pytest.mark.parametrize(
    ("question", "subject", "intent", "focus"),
    [
        ("inventory\uff0c哪些表在使用它", "inventory", "downstream", "table"),
        ("inventory\uff0c你看看哪些表在使用它", "inventory", "downstream", "table"),
        ("inventory\uff0c你看看它在使用哪些表", "inventory", "upstream", "table"),
        ("Regarding inventory, which tables read it?", "inventory", "downstream", "table"),
        (
            "Regarding inventory, could you tell me which tables read it?",
            "inventory",
            "downstream",
            "table",
        ),
        (
            "Regarding inventory, could you tell me which tables it reads?",
            "inventory",
            "upstream",
            "table",
        ),
        ("For inventory, please list the tables that use it.", "inventory", "downstream", "table"),
        ("For inventory, please list the tables that it uses.", "inventory", "upstream", "table"),
        ("inventory\uff0c请告诉我哪些表在使用它", "inventory", "downstream", "table"),
        ("inventory\uff0c请告诉我它在使用哪些表", "inventory", "upstream", "table"),
        (
            "inventory, before it feeds reports, which tables read it?",
            "inventory",
            "downstream",
            "table",
        ),
        (
            "inventory, before it reads reports, which tables does it feed?",
            "inventory",
            "downstream",
            "table",
        ),
    ],
)
def test_development_polite_topic_questions_bind_the_main_clause_pronoun(
    question: str, subject: str, intent: str, focus: str
) -> None:
    """Request framing and earlier subordinate pronouns do not change dependency direction."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert bool(parsed.intent_candidates) == (intent == "related")


@pytest.mark.parametrize(
    ("question", "subject", "intent", "focus"),
    [
        ("Which downstream tables does inventory read?", "inventory", "upstream", "table"),
        ("Which downstream tables read inventory?", "inventory", "downstream", "table"),
        ("Which upstream tables does inventory feed?", "inventory", "downstream", "table"),
        ("Which upstream tables feed inventory?", "inventory", "upstream", "table"),
        ("inventory 使用哪些下游表", "inventory", "upstream", "table"),
        ("哪些下游表使用 inventory", "inventory", "downstream", "table"),
        ("inventory 供给哪些上游表", "inventory", "downstream", "table"),
        ("哪些上游表供给 inventory", "inventory", "upstream", "table"),
        ("Which upstream tables is inventory consumed by?", "inventory", "downstream", "table"),
        ("Which downstream tables are consumed by inventory?", "inventory", "upstream", "table"),
        ("inventory 被哪些上游表使用", "inventory", "downstream", "table"),
        ("哪些下游表被 inventory 使用", "inventory", "upstream", "table"),
        ("Which upstream tables would fail without inventory?", "inventory", "downstream", "table"),
        ("Which downstream tables would inventory fail without?", "inventory", "upstream", "table"),
        (
            "Which upstream tables does inventory currently feed?",
            "inventory",
            "downstream",
            "table",
        ),
        ("Which downstream tables does inventory directly read?", "inventory", "upstream", "table"),
        ("inventory 正在使用哪些下游表", "inventory", "upstream", "table"),
        ("inventory 会供给哪些上游表", "inventory", "downstream", "table"),
    ],
)
def test_development_explicit_roles_override_hierarchy_adjectives(
    question: str, subject: str, intent: str, focus: str
) -> None:
    """A direct predicate, passive or absence condition binds more strongly than a noun modifier."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert bool(parsed.intent_candidates) == (intent == "related")


@pytest.mark.parametrize(
    ("question", "subject", "intent", "focus"),
    [
        ("Which tables are upstream from inventory?", "inventory", "upstream", "table"),
        ("Which tables are downstream from inventory?", "inventory", "downstream", "table"),
        ("inventory 上游有哪些表", "inventory", "upstream", "table"),
        ("inventory 下游有哪些表", "inventory", "downstream", "table"),
        ("inventory 的上游表有哪些\uff0c供给报表用的", "inventory", "upstream", "table"),
        ("inventory 的下游表有哪些\uff0c会读取底表的", "inventory", "downstream", "table"),
        (
            "Which upstream tables relate to inventory and feed reports?",
            "inventory",
            "upstream",
            "table",
        ),
        (
            "Which downstream tables relate to inventory and read reports?",
            "inventory",
            "downstream",
            "table",
        ),
        ("Which tables upstream of inventory feed reports?", "inventory", "upstream", "table"),
        ("Which tables downstream of inventory read reports?", "inventory", "downstream", "table"),
        ("What source tables relate to inventory?", "inventory", "upstream", "table"),
        ("What input reports relate to inventory?", "inventory", "downstream", "table"),
        ("What tables are associated with inventory?", "inventory", "related", "table"),
        ("What reports are associated with inventory?", "inventory", "downstream", "table"),
    ],
)
def test_development_weak_words_and_other_clauses_cannot_override_hierarchy(
    question: str, subject: str, intent: str, focus: str
) -> None:
    """Bare prepositions and predicates outside the subject relation preserve its hierarchy."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert bool(parsed.intent_candidates) == (intent == "related")


@pytest.mark.parametrize(
    ("question", "intent", "target", "counted"),
    [
        ("inventory 被哪几个团队维护的报表读取", "downstream", "view", False),
        ("inventory 由哪几个负责报表维护的团队管理", "owner", "team", False),
        ("inventory 被哪几张指标团队维护的报表读取", "downstream", "view", False),
        ("inventory 被多少个团队维护的指标读取", "downstream", "metric", True),
        ("inventory 被多少张团队维护的报表读取", "downstream", "view", True),
        ("多少个团队维护 inventory", "owner", "team", True),
        ("多少个报表维护团队负责 inventory", "owner", "team", True),
        ("inventory 对应哪些报表\uff0c团队的指标有哪些", "downstream", "view", False),
        ("inventory 对应哪些指标\uff0c团队的报表有哪些", "downstream", "metric", False),
        ("哪些团队读取 inventory 的指标", "downstream", "team", False),
        ("哪些报表读取 inventory 的指标", "downstream", "view", False),
        ("哪些指标读取 inventory 的报表", "downstream", "metric", False),
    ],
)
def test_development_counted_relative_heads_stop_at_subject_and_clause_boundaries(
    question: str, intent: str | None, target: str | None, *, counted: bool
) -> None:
    """Counted noun heads preserve directory types and remain inside their question."""
    parsed = registered_question(question, "inventory")
    if intent is None:
        assert parsed is None
        return
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert (parsed.count_focus is not None) == counted
    if parsed.count_focus is not None:
        assert parsed.count_focus.target_kind == target


@pytest.mark.parametrize(
    ("question", "intent", "target", "counted"),
    [
        ("inventory 表谁在使用", "downstream", "person", False),
        ("inventory 表谁在用", "downstream", "person", False),
        ("inventory 表谁在读", "downstream", "person", False),
        ("inventory 表给谁用", "downstream", "person", False),
        ("inventory 使用谁的数据", "upstream", "person", False),
        ("inventory 读取哪些表", "upstream", "table", False),
        ("inventory 哪些表在使用", "downstream", "table", False),
        ("inventory 哪些报表在读取", "downstream", "view", False),
        ("inventory 哪些指标在读取", "downstream", "metric", False),
        ("inventory 哪些人读过", "downstream", "person", False),
        ("inventory 哪些团队在用", "downstream", "team", False),
        ("哪些表给 inventory 用", "upstream", "table", False),
        ("谁在读取 inventory", "downstream", "person", False),
        ("inventory 读取谁的数据", "upstream", "person", False),
    ],
)
def test_development_omitted_topic_objects_do_not_reverse_consumer_roles(
    question: str, intent: str | None, target: str | None, *, counted: bool
) -> None:
    """A fronted resource with an interrogative consumer keeps downstream direction."""
    parsed = registered_question(question, "inventory")
    if intent is None:
        assert parsed is None
        return
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert (parsed.count_focus is not None) == counted
    if parsed.count_focus is not None:
        assert parsed.count_focus.target_kind == target


@pytest.mark.parametrize(
    ("question", "intent", "target", "counted"),
    [
        ("How many total teams own inventory?", "owner", "team", True),
        ("How many total metrics use inventory?", "downstream", "metric", True),
        ("How many total orders are in inventory?", None, None, False),
    ],
)
def test_development_quantity_modifiers_preserve_catalog_and_business_counts(
    question: str, intent: str | None, target: str | None, *, counted: bool
) -> None:
    """Total modifies the counted head without turning directory objects into business measures."""
    parsed = registered_question(question, "inventory")
    if intent is None:
        assert parsed is None
        return
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert (parsed.count_focus is not None) == counted
    if parsed.count_focus is not None:
        assert parsed.count_focus.target_kind == target
