# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure development regressions for topic pronouns and nonrelational request framing."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("inventory_units, which tables read it?", "inventory_units", "downstream"),
        ("inventory_units, which tables does it read?", "inventory_units", "upstream"),
        ("For inventory_units, what tables use it?", "inventory_units", "downstream"),
        ("For inventory_units, what tables does it use?", "inventory_units", "upstream"),
        ("inventory_units, which source tables feed it?", "inventory_units", "upstream"),
        ("inventory_units, which tables does it feed?", "inventory_units", "downstream"),
        ("请给我列一下 inventory 关联的报表有哪些", "inventory", "downstream"),
        ("给我看看 inventory_units 供给哪些表", "inventory_units", "downstream"),
        ("请给我看看 inventory 对应哪些指标", "inventory", "downstream"),
        ("请从目录看看 inventory 对应哪些报表", "inventory", "downstream"),
        ("From the catalog, what reports relate to inventory?", "inventory", "downstream"),
        ("From the catalog, what tables relate to inventory_units?", "inventory_units", "upstream"),
        ("From which tables is inventory built?", "inventory", "upstream"),
        ("从哪些表加工出来的 inventory", "inventory", "upstream"),
        ("哪些表给 inventory 供数", "inventory", "upstream"),
        ("inventory 给哪些表供数", "inventory", "downstream"),
    ],
)
def test_development_framing_cannot_supply_a_dependency_role(
    question: str, subject: str, intent: str
) -> None:
    """Only the subject's role in the requested relation determines its direction."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize(
    ("question", "target", "counted"),
    [
        ("inventory 关联的指标报表有哪些", "view", False),
        ("inventory 关联的报表指标有哪些", "metric", False),
        ("inventory 给几个指标报表供数", "view", True),
        ("inventory 给几个报表指标供数", "metric", True),
        ("inventory 供给哪些数据表", "table", False),
        ("inventory 供给多少张数据表", "table", True),
    ],
)
def test_development_compound_noun_head_follows_language_order(
    question: str, target: str, *, counted: bool
) -> None:
    """Adjacent catalog nouns are compounds; an overlapping lexical noun stays indivisible."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == "downstream"
    assert parsed.intent_candidates == ()
    assert parsed.recognition.focus == ("metric" if target == "metric" else "table")
    if counted:
        assert parsed.count_focus is not None
        assert parsed.count_focus.target_kind == target
    else:
        assert parsed.count_focus is None


@pytest.mark.parametrize(
    ("question", "target"),
    [
        ("How many teams use inventory to forecast purchases?", "team"),
        ("How many people read inventory before they buy products?", "person"),
        ("How many teams read inventory to forecast sales?", "team"),
        ("How many people use inventory after they purchased products?", "person"),
    ],
)
def test_development_business_words_outside_the_main_predicate_preserve_catalog_count(
    question: str, target: str
) -> None:
    """The requested users remain catalog objects when a later clause mentions commerce."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == "downstream"
    assert parsed.count_focus is not None
    assert parsed.count_focus.target_kind == target


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("inventory_units, which tables have it as their input?", "inventory_units", "downstream"),
        ("inventory, which metrics have it as their output?", "inventory", "upstream"),
    ],
)
def test_development_topic_pronoun_preserves_nominal_role_boundaries(
    question: str, subject: str, intent: str
) -> None:
    """Replacing an entire pronoun keeps the source/result template and original coordinates."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.rule_id == "K11-subject-role"
    assert parsed.intent_candidates == ()
