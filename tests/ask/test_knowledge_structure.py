# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure development cases exercise grammatical roles and scope, never sealed evaluation data."""

import pytest

from tests.ask.parsing_helpers import registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("哪些表支撑 inventory_units 的计算", "inventory_units", "upstream"),
        ("inventory_units 支撑的表有哪些", "inventory_units", "downstream"),
        ("由 inventory_units 生成的表有哪些", "inventory_units", "downstream"),
        ("inventory_units 是由哪些表生成的", "inventory_units", "upstream"),
        ("拿 inventory_units 作输入来构建的表是哪些", "inventory_units", "downstream"),
        ("作为输入的 inventory_units 被哪些表读取", "inventory_units", "downstream"),
        ("inventory_units 是哪些表的输入", "inventory_units", "downstream"),
        ("哪些表是 inventory_units 的输入", "inventory_units", "upstream"),
        ("inventory 是哪些指标的输出", "inventory", "upstream"),
        ("哪些指标是 inventory 的输出", "inventory", "downstream"),
        ("哪些表给 inventory_units 供数", "inventory_units", "upstream"),
        ("inventory_units 给哪些表供数", "inventory_units", "downstream"),
        ("谁会把 inventory_units 拿来当依据", "inventory_units", "downstream"),
        ("inventory_units 到底被谁消费了", "inventory_units", "downstream"),
        ("inventory_units 到底消费了谁的数据", "inventory_units", "upstream"),
        ("inventory_units 由谁负责维护", "inventory_units", "owner"),
        ("Which tables are powered by inventory_units?", "inventory_units", "downstream"),
        ("Which tables is inventory_units powered by?", "inventory_units", "upstream"),
        ("Which tables support inventory_units?", "inventory_units", "upstream"),
        ("Which tables does inventory_units support?", "inventory_units", "downstream"),
        ("What is supported by inventory_units?", "inventory_units", "downstream"),
        ("What is inventory_units supported by?", "inventory_units", "upstream"),
        ("Which tables are produced from inventory_units?", "inventory_units", "downstream"),
        ("Which metrics produce inventory?", "inventory", "upstream"),
        ("Which metrics does inventory produce?", "inventory", "downstream"),
        ("inventory_units is an input for which tables?", "inventory_units", "downstream"),
        ("Which tables is inventory_units an input for?", "inventory_units", "downstream"),
        ("Which tables have inventory_units as their input?", "inventory_units", "downstream"),
        ("inventory is the output of which metrics?", "inventory", "upstream"),
        ("Which metrics have inventory as their output?", "inventory", "upstream"),
        ("Who has been reading inventory_units?", "inventory_units", "downstream"),
        ("Who is inventory_units being consumed by?", "inventory_units", "downstream"),
        ("Who is responsible for maintaining inventory_units?", "inventory_units", "owner"),
        ("Which tables pull their data from inventory_units?", "inventory_units", "downstream"),
        ("inventory_units pulls its data from which tables?", "inventory_units", "upstream"),
        ("What data does inventory_units feed into?", "inventory_units", "downstream"),
    ],
)
def test_development_source_and_result_roles_preserve_relation_direction(
    question: str, subject: str, intent: str
) -> None:
    """Active, passive and nominal roles override a contradictory catalog-level default."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()
    assert parsed.candidates[0].name == subject


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("会受到 inventory_units 变化影响的表有哪些", "inventory_units", "downstream"),
        ("inventory_units 会受到哪些表的变化影响", "inventory_units", "upstream"),
        ("哪些表会因 inventory_units 变化而受到影响", "inventory_units", "downstream"),
        ("inventory_units 会因哪些表变化而受影响", "inventory_units", "upstream"),
        ("受 inventory_units 牵连的表是哪些", "inventory_units", "downstream"),
        ("inventory_units 受哪些表牵连", "inventory_units", "upstream"),
        ("哪些表出故障会让 inventory_units 不可用", "inventory_units", "upstream"),
        ("inventory_units 出故障会让哪些表不可用", "inventory_units", "downstream"),
        ("如果哪些表下线\uff0cinventory_units 会无法计算", "inventory_units", "upstream"),
        ("如果 inventory_units 下线\uff0c哪些表会无法计算", "inventory_units", "downstream"),
        ("若没有 inventory_units\uff0c受影响的是哪些表", "inventory_units", "downstream"),
        ("inventory_units 要是没了\uff0c受牵连的表有哪些", "inventory_units", "downstream"),
        (
            "Which tables would be affected if inventory_units vanished?",
            "inventory_units",
            "downstream",
        ),
        ("If which tables disappeared would inventory_units fail?", "inventory_units", "upstream"),
        ("What data would inventory_units fail without?", "inventory_units", "upstream"),
        (
            "Without inventory_units, what data would become unavailable?",
            "inventory_units",
            "downstream",
        ),
        ("What would cause inventory_units to fail?", "inventory_units", "upstream"),
        ("What would inventory_units cause to fail?", "inventory_units", "downstream"),
        (
            "Which tables depend on inventory_units, which feeds a report?",
            "inventory_units",
            "downstream",
        ),
        (
            "Which tables does inventory_units, which feeds a report, depend on?",
            "inventory_units",
            "upstream",
        ),
        (
            "inventory_units, which reads a source table, powers what tables?",
            "inventory_units",
            "downstream",
        ),
        (
            "inventory_units, which powers a dashboard, reads what tables?",
            "inventory_units",
            "upstream",
        ),
        (
            "Although inventory_units powers reports, what tables does it read?",
            "inventory_units",
            "upstream",
        ),
        (
            "Although inventory_units reads tables, what tables does it power?",
            "inventory_units",
            "downstream",
        ),
        ("inventory_units 虽然供给报表\uff0c但它依赖的表有哪些", "inventory_units", "upstream"),
        ("inventory_units 虽然依赖底表\uff0c但它供给的表有哪些", "inventory_units", "downstream"),
        ("作为报表输入的 inventory_units\uff0c其来源表有哪些", "inventory_units", "upstream"),
        ("来自若干表的 inventory_units\uff0c它的下游表有哪些", "inventory_units", "downstream"),
        ("作为表的输入\uff0cinventory_units 还依赖哪些表", "inventory_units", "upstream"),
        (
            "What tables read inventory_units after it is built from source data?",
            "inventory_units",
            "downstream",
        ),
        (
            "What tables does inventory_units read before it feeds reports?",
            "inventory_units",
            "upstream",
        ),
        (
            "What tables feed inventory_units before it is used by reports?",
            "inventory_units",
            "upstream",
        ),
    ],
)
def test_development_question_scope_selects_the_requested_relationship(
    question: str, subject: str, intent: str
) -> None:
    """Causality and subordinate clauses cannot invert the relation carrying the question."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize(
    ("question", "subject", "intent", "focus"),
    [
        (
            "读取 sales_summary 中数据的指标\uff0c具体是哪些",
            "sales_summary",
            "downstream",
            "metric",
        ),
        ("sales_summary 中数据所对应的指标都有什么", "sales_summary", "downstream", "metric"),
        (
            "sales_summary 对应的指标\uff0c在报表里列的是哪些",
            "sales_summary",
            "downstream",
            "metric",
        ),
        ("sales_summary 对应哪些用于报表的指标", "sales_summary", "downstream", "metric"),
        ("sales_summary 对应哪些由团队维护的指标", "sales_summary", "downstream", "metric"),
        ("sales_summary 对应哪些用来展示指标的报表", "sales_summary", "related", "table"),
        ("sales_summary 的数据由哪个维护指标的团队负责", "sales_summary", "owner", "person"),
        ("维护 sales_summary 数据的团队具体有哪些", "sales_summary", "owner", "person"),
        ("inventory 相关的供团队查看的报表有哪些", "inventory", "downstream", "table"),
        ("inventory 由哪个负责指标的团队维护", "inventory", "owner", "person"),
        (
            "What metrics associated with sales_summary appear in dashboards?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        (
            "What dashboard metrics relate to sales_summary?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        (
            "What metrics for dashboards relate to sales_summary?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        (
            "What metrics maintained by teams relate to sales_summary?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        (
            "What team that maintains metrics also maintains sales_summary?",
            "sales_summary",
            "owner",
            "person",
        ),
        ("Which tables for dashboards feed sales_summary?", "sales_summary", "upstream", "table"),
        ("Which dashboard tables feed sales_summary?", "sales_summary", "upstream", "table"),
        (
            "For sales_summary, what are its related metrics?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        ("For inventory, what are the associated dashboards?", "inventory", "downstream", "table"),
        (
            "The metrics related to sales_summary are which ones?",
            "sales_summary",
            "downstream",
            "metric",
        ),
        ("What are the teams that look after inventory?", "inventory", "owner", "person"),
        ("What source data is underneath sales_summary?", "sales_summary", "upstream", "table"),
        ("sales_summary 的表有哪些", "sales_summary", "upstream", "table"),
        ("inventory 的表有哪些", "inventory", "related", "table"),
    ],
)
def test_development_focus_uses_the_head_of_the_question_phrase(
    question: str, subject: str, intent: str, focus: str
) -> None:
    """Requested nouns win over incidental types inside attributes and relative clauses."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.focus == focus
    assert bool(parsed.intent_candidates) == (intent == "related")
