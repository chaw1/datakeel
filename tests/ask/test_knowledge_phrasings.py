# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent bilingual paraphrases test compositional intent and subject boundaries."""

import pytest

from tests.ask.parsing_helpers import registered_question

POSITIVE_PHRASINGS = [
    ("谁是退款额的负责人", "owner", "退款额"),
    ("出货额是谁在维护?", "owner", "出货额"),
    ("出货额谁管?", "owner", "出货额"),
    ("哪个团队负责出货额?", "owner", "出货额"),
    ("请问哪位维护库存量呢?", "owner", "库存量"),
    ("零售额的所有者是谁", "owner", "零售额"),
    ("谁维护了库存量", "owner", "库存量"),
    ("哪位同事管理过零售额", "owner", "零售额"),
    ("出货额由哪个部门负责", "owner", "出货额"),
    ("维修费用的数据来源是什么", "upstream", "维修费用"),
    ("零售额依赖哪些表", "upstream", "零售额"),
    ("库存量的上游是哪张表?", "upstream", "库存量"),
    ("库存量由哪些表加工而来?", "upstream", "库存量"),
    ("sales_summary 是从哪张表来的", "upstream", "sales_summary"),
    ("库存摘要来源于哪张表", "upstream", "库存摘要"),
    ("库存摘要源于哪些表", "upstream", "库存摘要"),
    ("库存摘要取自什么数据表", "upstream", "库存摘要"),
    ("库存摘要用哪张表算", "upstream", "库存摘要"),
    ("库存摘要使用过哪些表", "upstream", "库存摘要"),
    ("库存摘要基于哪张表计算出来的", "upstream", "库存摘要"),
    ("出货额日报从哪来", "upstream", "出货额日报"),
    ("哪些表是库存摘要的上游", "upstream", "库存摘要"),
    ("哪些表用到了库存摘要", "downstream", "库存摘要"),
    ("哪些指标使用过库存摘要", "downstream", "库存摘要"),
    ("库存摘要被哪些指标使用", "downstream", "库存摘要"),
    ("库存摘要的下游是什么", "downstream", "库存摘要"),
    ("依赖库存摘要的有哪些", "downstream", "库存摘要"),
    ("库存摘要影响哪些指标", "downstream", "库存摘要"),
    ("基于库存摘要的指标有哪些", "downstream", "库存摘要"),
    ("周岩都负责哪些", "owned", "周岩"),
    ("周岩也维护什么表呢", "owned", "周岩"),
    ("周岩管哪些", "owned", "周岩"),
    ("周岩负责的指标有哪些", "owned", "周岩"),
    ("orders 团队负责哪些", "owned", "orders 团队"),
    ("供应链负责人也维护哪些数据表", "owned", "供应链负责人"),
    ("who's the owner of inventory_units", "owner", "inventory_units"),
    ("who is in charge of inventory_units", "owner", "inventory_units"),
    ("which team owns inventory_units", "owner", "inventory_units"),
    ("Which department maintains inventory_units?", "owner", "inventory_units"),
    ("Who is inventory_units' owner?", "owner", "inventory_units"),
    ("Who is responsible for inventory_units?", "owner", "inventory_units"),
    ("what feeds inventory_units", "upstream", "inventory_units"),
    ("what is the source of inventory_units", "upstream", "inventory_units"),
    ("where is inventory_units from", "upstream", "inventory_units"),
    ("what does inventory_units depend on", "upstream", "inventory_units"),
    ("what is upstream of inventory_units", "upstream", "inventory_units"),
    ("what is inventory_units based on", "upstream", "inventory_units"),
    ("Which tables feed inventory_units?", "upstream", "inventory_units"),
    ("What is inventory_units computed from?", "upstream", "inventory_units"),
    ("Where does inventory_units come from?", "upstream", "inventory_units"),
    ("What are the sources of inventory_units?", "upstream", "inventory_units"),
    ("What does inventory_units use?", "upstream", "inventory_units"),
    ("What does inventory_units consume?", "upstream", "inventory_units"),
    ("what depends on inventory_units", "downstream", "inventory_units"),
    ("what is downstream of inventory_units", "downstream", "inventory_units"),
    ("what consumes inventory_units", "downstream", "inventory_units"),
    ("Which dashboards use inventory_units?", "downstream", "inventory_units"),
    ("Which metrics are derived from inventory_units?", "downstream", "inventory_units"),
    ("What uses inventory_units?", "downstream", "inventory_units"),
    ("What is inventory_units used by?", "downstream", "inventory_units"),
    ("what is Morgan responsible for", "owned", "Morgan"),
    ("What does the Operations team maintain?", "owned", "Operations team"),
    ("Which metrics does Morgan own?", "owned", "Morgan"),
    ("What does Morgan manage?", "owned", "Morgan"),
    ("负责出货额的团队是哪个?", "owner", "出货额"),
    ("出货额现在是谁负责的?", "owner", "出货额"),
    ("出货额依赖的源表是哪些?", "upstream", "出货额"),
    ("哪些视图是依赖orders计算出来的?", "downstream", "orders"),
    ("orders是由哪个指标用到的?", "downstream", "orders"),
    ("Ops Crew所管理的表有哪些?", "owned", "Ops Crew"),
    ("Who currently maintains retention?", "owner", "retention"),
    ("Can you tell me who retention is maintained by?", "owner", "retention"),
    ("Which source tables does retention depend on?", "upstream", "retention"),
    ("What sources feed retention?", "upstream", "retention"),
    ("Which tables are maintained by Ops Crew?", "owned", "Ops Crew"),
    ("inventory_units uses what?", "upstream", "inventory_units"),
    ("inventory_units depends on what?", "upstream", "inventory_units"),
    ("inventory_units is used by what?", "downstream", "inventory_units"),
    ("谁负责的销售总额", "owner", "销售总额"),
    ("负责人维护哪些排名前几的指标", "owned", "负责人"),
]

NUMERIC_PHRASINGS = [
    "上个季度华东区基于开票的销售额是多少",
    "2026年3月来源于线上的零售额是多少",
    "2026年3月用到优惠券的成交订单数是多少",
    "华东区负责的客户数量是多少",
    "2026年3月下游渠道的出货额是多少",
    "2026年3月维护期内的维修费用是多少",
    "谁负责的门店销售额最高",
    "who owns the most orders",
    "哪位负责的门店订单最少",
    "按负责人统计合计出货额",
    "依赖渠道有几个客户",
    "来源渠道的销售额排名",
    "下游客户数量最低的是哪个渠道",
    "How much revenue comes from downstream channels?",
    "How many orders does Morgan own?",
    "What is the total revenue for this owner?",
    "Which owner has the least revenue?",
    "Who owns the top stores?",
    "谁负责的门店销售额最多",
    "Show sales for downstream channels",
]


@pytest.mark.parametrize(("question", "intent", "subject"), POSITIVE_PHRASINGS)
def test_composed_paraphrases_resolve_intent_and_subject(
    question: str, intent: str, subject: str
) -> None:
    """Relation vocabulary composes with actor, direction, filler and subject clauses."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert (parsed.intent, parsed.unsupported_phrasing) == (intent, False)
    assert len(parsed.candidates) == 1
    assert parsed.candidates[0].name == subject


@pytest.mark.parametrize("question", NUMERIC_PHRASINGS)
def test_quantity_and_ranking_always_take_metric_route(question: str) -> None:
    """Quantitative cues win even when interrogatives and ownership words are present."""
    assert registered_question(question) is None


@pytest.mark.parametrize(
    "question",
    [
        "Who owns?",
        "谁负责",
        "由谁负责的",
        "谁能解释这个异常",
        "哪位可以说明这个情况",
        "来源?",
        "Tell me about the owner",
        "We need to know what depends on",
    ],
)
def test_strong_knowledge_clues_never_fall_through_to_numeric_execution(question: str) -> None:
    """Knowledge cues without a registered subject request suggestions, never metric execution."""
    parsed = registered_question(question)
    assert parsed is not None
    assert parsed.recognition.rule_id == "K0-unknown-subject"
    assert parsed.candidates == ()
    assert parsed.subject == ""


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("Who could help with inventory_units?", "inventory_units", "owner"),
        ("库存量来源还有哪些细节需要核实", "库存量", "upstream"),
    ],
)
def test_registered_subject_and_typed_focus_do_not_require_a_known_verb(
    question: str, subject: str, intent: str
) -> None:
    """Requested answer types and explicit directions can resolve unfamiliar phrasing."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        ("请问", "呢?"),
        ("请告诉我", "呀"),
        ("麻烦问下", "啊"),
        ("我想知道", ""),
    ],
)
def test_particle_combinations_do_not_change_graph_subject(prefix: str, suffix: str) -> None:
    """A quoted entity remains intact across optional framing and verb aspect particles."""
    parsed = registered_question(f"{prefix}哪些表用到了『季度库存摘要』{suffix}", "季度库存摘要")
    assert parsed is not None
    assert (parsed.intent, parsed.subject) == ("downstream", "季度库存摘要")
