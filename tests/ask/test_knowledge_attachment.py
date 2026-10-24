# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind restrictive attributes to the requested head before resolving asset predicates."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        pytest.param(
            "inventory, which teams that maintain reports use it?",
            "downstream",
            id="topic-owner-relative-consumer-main",
        ),
        pytest.param(
            "inventory, which teams that use reports maintain it?",
            "owner",
            id="topic-consumer-relative-owner-main",
        ),
        pytest.param(
            "inventory, which tables that feed reports read it?",
            "downstream",
            id="topic-source-relative-consumer-main",
        ),
        pytest.param(
            "inventory\uff0c哪些维护报表的团队使用它",
            "downstream",
            id="zh-topic-owner-relative-consumer-main",
        ),
        pytest.param("Which teams maintain inventory?", "owner", id="owner-control"),
        pytest.param("Which teams use inventory?", "downstream", id="consumer-control"),
        pytest.param(
            "Which teams that maintain reports use inventory?",
            "downstream",
            id="owner-modifier-consumer-main",
        ),
        pytest.param(
            "Which teams that use reports maintain inventory?",
            "owner",
            id="consumer-modifier-owner-main",
        ),
        pytest.param(
            "哪些维护报表的团队使用 inventory", "downstream", id="zh-owner-modifier-consumer-main"
        ),
        pytest.param(
            "哪些使用报表的团队维护 inventory", "owner", id="zh-consumer-modifier-owner-main"
        ),
        pytest.param("Which tables feed inventory?", "upstream", id="source-control"),
        pytest.param("Which tables read inventory?", "downstream", id="destination-control"),
        pytest.param(
            "Which tables that feed reports read inventory?",
            "downstream",
            id="source-modifier-destination-main",
        ),
        pytest.param(
            "Which tables that read reports feed inventory?",
            "upstream",
            id="destination-modifier-source-main",
        ),
        pytest.param(
            "Which tables that inventory reads feed reports?",
            "upstream",
            id="subject-in-relative-object",
        ),
        pytest.param(
            "Which tables that inventory feeds read reports?",
            "downstream",
            id="subject-in-relative-source",
        ),
        pytest.param(
            "Which teams who maintain reports use inventory?",
            "downstream",
            id="owner-relative-consumer-main-who",
        ),
        pytest.param(
            "Which teams who use reports maintain inventory?",
            "owner",
            id="consumer-relative-owner-main-who",
        ),
        pytest.param(
            "Which teams that maintain inventory use reports?",
            "owner",
            id="subject-in-owner-relative",
        ),
        pytest.param(
            "Which teams that use inventory maintain reports?",
            "downstream",
            id="subject-in-consumer-relative",
        ),
        pytest.param(
            "Which teams that inventory uses maintain reports?",
            "upstream",
            id="subject-uses-team-relative",
        ),
        pytest.param(
            "Which tables that feed reports does inventory read?",
            "upstream",
            id="subject-in-main-inversion-read",
        ),
        pytest.param(
            "Which tables that read reports does inventory feed?",
            "downstream",
            id="subject-in-main-inversion-feed",
        ),
        pytest.param("Which tables does inventory read?", "upstream", id="inversion-read-control"),
        pytest.param(
            "Which tables does inventory feed?", "downstream", id="inversion-feed-control"
        ),
        pytest.param(
            "inventory reads which tables that feed reports?",
            "upstream",
            id="subject-before-focus-read",
        ),
        pytest.param(
            "inventory feeds which tables that read reports?",
            "downstream",
            id="subject-before-focus-feed",
        ),
        pytest.param("哪些维护 inventory 的团队使用报表", "owner", id="zh-owner-relative-known"),
        pytest.param(
            "哪些使用 inventory 的团队维护报表", "downstream", id="zh-consumer-relative-known"
        ),
        pytest.param(
            "哪些 inventory 供给的表读取报表", "downstream", id="zh-known-role-relative-source"
        ),
        pytest.param(
            "哪些供给 inventory 的表读取报表", "upstream", id="zh-known-role-relative-result"
        ),
        pytest.param(
            "哪些读取 inventory 的表供给报表", "downstream", id="zh-known-role-relative-read"
        ),
        pytest.param(
            "inventory 使用哪些供给报表的表", "upstream", id="zh-subject-before-focus-read"
        ),
        pytest.param(
            "inventory 供给哪些读取报表的表", "downstream", id="zh-subject-before-focus-feed"
        ),
        pytest.param(
            "How many teams that maintain reports use inventory?",
            "downstream",
            id="count-owner-relative-consumer-main",
        ),
        pytest.param(
            "How many teams that use reports maintain inventory?",
            "owner",
            id="count-consumer-relative-owner-main",
        ),
        pytest.param(
            "多少个维护报表的团队使用 inventory",
            "downstream",
            id="zh-count-owner-relative-consumer-main",
        ),
        pytest.param(
            "多少个使用报表的团队维护 inventory",
            "owner",
            id="zh-count-consumer-relative-owner-main",
        ),
    ],
)
def test_restrictive_attribute_binds_the_predicate_containing_the_asset(
    question: str, intent: str
) -> None:
    """A relative or main clause contributes direction only when its relation uses the asset."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    if question.startswith(("How many", "多少")):
        assert parsed.count_focus is not None
        assert parsed.count_focus.target_kind == "team"


@pytest.mark.parametrize(
    ("question", "intent", "focus"),
    [
        ("Among the metrics related to inventory, which ones use it?", "downstream", "metric"),
        ("Among the views related to inventory, which ones read it?", "downstream", "table"),
        ("Among the people associated with inventory, which ones own it?", "owner", "person"),
        ("Among the metrics related to inventory, which of them use it?", "downstream", "metric"),
        ("What tables feed inventory, which supplies metrics?", "upstream", "table"),
        ("What tables read inventory, which consumes metrics?", "downstream", "table"),
    ],
)
def test_partitive_head_and_supplementary_relative_keep_the_main_question(
    question: str, intent: str, focus: str
) -> None:
    """An interrogative placeholder retains its antecedent type without promoting side clauses."""
    parsed = registered_question(question, "inventory")
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert parsed.intent_candidates == ()
