# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Direction regressions distinguish catalog hierarchy from explicit grammatical roles."""

from tests.ask.parsing_helpers import registered_question


def test_catalog_hierarchy_infers_both_directions_and_preserves_same_layer_ambiguity() -> None:
    """An unqualified cross-layer list follows dependency levels; a peer list stays unclear."""
    examples = (
        ("inventory 相关的看板有哪些?", "inventory", "downstream"),
        ("sales_summary 对应什么表?", "sales_summary", "upstream"),
        ("revenue metric 对应哪些视图?", "revenue metric", "upstream"),
        ("Which metrics relate to sales_summary?", "sales_summary", "downstream"),
    )
    for question, subject, expected in examples:
        parsed = registered_question(question, subject)
        assert parsed is not None
        assert parsed.intent == expected
        assert not parsed.intent_candidates
        assert parsed.candidates[0].name == subject
    ambiguous = registered_question("inventory 对应哪些表?", "inventory")
    assert ambiguous is not None
    assert ambiguous.intent == "related"
    assert set(ambiguous.intent_candidates) == {"upstream", "downstream"}


def test_subject_source_and_result_roles_override_hierarchy_in_both_languages() -> None:
    """Known inputs point to their consumers, while known outputs point to their sources."""
    examples = (
        ("把 inventory 当作基础的还有哪些?", "inventory", "downstream"),
        ("inventory 的源头有哪些?", "inventory", "upstream"),
        ("哪些表用 revenue metric 作为输入?", "revenue metric", "downstream"),
        ("sales_summary 是用哪些指标加工出来的?", "sales_summary", "upstream"),
        ("What is fed by inventory?", "inventory", "downstream"),
        ("What is inventory fed by?", "inventory", "upstream"),
        ("Which tables does revenue metric power?", "revenue metric", "downstream"),
        ("Which metrics is sales_summary built on?", "sales_summary", "upstream"),
    )
    for question, subject, expected in examples:
        parsed = registered_question(question, subject)
        assert parsed is not None
        assert parsed.intent == expected
        assert parsed.recognition.direction == expected
        assert not parsed.intent_candidates
        assert parsed.candidates[0].name == subject
