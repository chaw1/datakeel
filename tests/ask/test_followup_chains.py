# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent bilingual chains compare follow-ups to equivalent standalone questions."""

from datetime import UTC, datetime

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)

CHAINS = (
    ("上个季度华东区零售额是多少", (("那华南呢", "上个季度华南零售额"),)),
    ("上个季度华南零售额", (("那华北呢", "上个季度华北零售额"),)),
    ("上个月华东零售额", (("那西部呢", "上个月西部零售额"),)),
    ("去年华北销售额", (("那华南呢", "去年华南销售额"),)),
    ("上个季度华东出货额", (("那西部呢", "上个季度西部出货额"),)),
    ("上个季度华东订单数", (("那华南呢", "上个季度华南订单数"),)),
    (
        "last quarter retail revenue in East China",
        (("what about South China", "last quarter retail revenue in South China"),),
    ),
    (
        "last month retail revenue in South China",
        (("what about North China", "last month retail revenue in North China"),),
    ),
    (
        "last quarter sales amount in East China",
        (("what about West China", "last quarter sales amount in West China"),),
    ),
    ("上个季度华东零售额", (("上个月呢", "上个月华东零售额"),)),
    ("上个月华南订单数", (("去年呢", "去年华南订单数"),)),
    ("去年华北销售额", (("上个季度呢", "上个季度华北销售额"),)),
    (
        "last quarter retail revenue in East China",
        (("last month", "last month retail revenue in East China"),),
    ),
    (
        "last month sales amount in North China",
        (("last year", "last year sales amount in North China"),),
    ),
    ("上个季度零售额", (("按区域拆开", "上个季度按零售区域零售额"),)),
    ("上个季度零售额", (("按月拆开", "上个季度按月零售额"),)),
    ("上个季度订单数", (("按月拆开", "上个季度按月订单数"),)),
    ("去年销售额", (("按月拆开", "去年按月销售额"),)),
    ("last quarter retail revenue", (("by region", "last quarter retail revenue by region"),)),
    ("last quarter order count", (("by month", "last quarter order count by month"),)),
    ("last year retail revenue", (("monthly", "last year retail revenue monthly"),)),
    ("上个季度华东零售额", (("换成订单数", "上个季度华东订单数"),)),
    ("上个月华南订单数", (("换成零售额", "上个月华南零售额"),)),
    (
        "last quarter retail revenue in East China",
        (("switch to order count", "last quarter order count in East China"),),
    ),
    (
        "last month order count in South China",
        (("change to retail revenue", "last month retail revenue in South China"),),
    ),
    ("上个季度华东零售额", (("同比", "上个季度华东零售额同比"),)),
    ("上个月华南订单数", (("环比", "上个月华南订单数环比"),)),
    (
        "last quarter retail revenue",
        (("year over year", "last quarter retail revenue year over year"),),
    ),
    (
        "上个季度华东零售额",
        (("那华南呢", "上个季度华南零售额"), ("上个月呢", "上个月华南零售额")),
    ),
    (
        "上个季度华东零售额",
        (("换成订单数", "上个季度华东订单数"), ("那华北呢", "上个季度华北订单数")),
    ),
    (
        "last quarter retail revenue in East China",
        (
            ("what about South China", "last quarter retail revenue in South China"),
            ("last month", "last month retail revenue in South China"),
        ),
    ),
    (
        "上个季度零售额",
        (("按月拆开", "上个季度按月零售额"), ("换成订单数", "上个季度按月订单数")),
    ),
    ("上个季度各区域零售额", (("那华南呢", "上个季度华南零售额"),)),
    ("上个月按零售渠道订单数", (("那门店呢", "上个月门店订单数"),)),
    (
        "last quarter retail revenue by region",
        (("what about South China", "last quarter retail revenue in South China"),),
    ),
    (
        "last quarter retail revenue in East China",
        (("what about August 2026", "retail revenue in East China in August 2026"),),
    ),
    (
        "last quarter retail revenue in East China",
        (("what about 2026 Q3", "retail revenue in East China in 2026 Q3"),),
    ),
    (
        "last quarter retail revenue in East China",
        (("what about stores", "last quarter retail revenue in East China in stores"),),
    ),
    (
        "last quarter retail revenue in East China",
        (
            ("what about August 2026", "retail revenue in East China in August 2026"),
            ("what about September 2026", "retail revenue in East China in September 2026"),
        ),
    ),
)


@pytest.mark.parametrize(("initial", "turns"), CHAINS)
def test_followups_equal_complete_questions(
    db: Database,
    enterprise_sample: EnterpriseSample,
    initial: str,
    turns: tuple[tuple[str, str], ...],
) -> None:
    """Each turn must produce the same numeric rows and frame as its full question."""
    first = ask_data(db, AskRequest(question=initial, reference_instant=REFERENCE))
    assert first.status == "answered", initial
    assert first.interpreted_question
    conversation_id = first.conversation_id
    assert conversation_id
    for followup, complete in turns:
        answer = ask_data(
            db,
            AskRequest(
                question=followup,
                conversation_id=conversation_id,
                reference_instant=REFERENCE,
            ),
        )
        standalone = ask_data(db, AskRequest(question=complete, reference_instant=REFERENCE))
        assert answer.status == standalone.status == "answered", (followup, answer.message)
        assert answer.result == standalone.result, (followup, complete)
        assert answer.query_frame == standalone.query_frame, (followup, complete)
        assert answer.interpreted_question
        assert answer.conversation_id == conversation_id


@pytest.mark.parametrize(
    "question",
    [
        "再详细点",
        "那边呢",
        "另外那个呢",
        "what about it",
        "same again but better",
        "compare with something else",
    ],
)
def test_ambiguous_followup_never_emits_numbers(
    db: Database, enterprise_sample: EnterpriseSample, question: str
) -> None:
    """Unresolved references cannot silently reuse a previous numeric query."""
    first = ask_data(db, AskRequest(question="上个季度零售额", reference_instant=REFERENCE))
    answer = ask_data(
        db,
        AskRequest(
            question=question,
            conversation_id=first.conversation_id,
            reference_instant=REFERENCE,
        ),
    )
    assert answer.status == "clarification"
    assert answer.result is None
    assert answer.sql is None
    assert answer.interpreted_question


@pytest.mark.parametrize(
    "topic",
    ["订单数是多少", "上个月销售额是多少", "出货额是多少", "Show sales amount", "Retail units"],
)
def test_complete_new_topic_clears_previous_frame(
    db: Database, enterprise_sample: EnterpriseSample, topic: str
) -> None:
    """A fresh explicit question must not retain old filters, grouping or dates."""
    first = ask_data(
        db, AskRequest(question="上个季度华南按零售渠道零售额", reference_instant=REFERENCE)
    )
    answer = ask_data(
        db,
        AskRequest(
            question=topic,
            conversation_id=first.conversation_id,
            reference_instant=REFERENCE,
        ),
    )
    standalone = ask_data(db, AskRequest(question=topic, reference_instant=REFERENCE))
    assert answer.status == standalone.status == "answered"
    assert answer.result == standalone.result
    assert answer.query_frame == standalone.query_frame
    assert answer.interpreted_question


def test_unregistered_concepts_in_a_conversation_answer_like_standalone_questions(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A sentence without any edit cue never inherits the previous metric as a follow-up."""
    for question in (
        "退货率为什么上升",
        "客户满意度如何",
        "下个月市场份额会是多少",
        "品牌知名度提高了多少",
    ):
        first = ask_data(
            db, AskRequest(question="上个季度华东区零售额是多少", reference_instant=REFERENCE)
        )
        answer = ask_data(
            db,
            AskRequest(
                question=question,
                conversation_id=first.conversation_id,
                reference_instant=REFERENCE,
            ),
        )
        standalone = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
        assert answer.status == standalone.status == "unanswerable", (question, answer.message)
        assert answer.message == standalone.message
        assert len(answer.candidates) == len(standalone.candidates) == 3
        assert answer.result is None
        assert answer.query_frame is None


def test_sliced_followup_drops_the_inherited_grouping_and_keeps_other_groups(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Filtering a grouped dimension yields one value; unrelated groupings survive."""
    first = ask_data(
        db, AskRequest(question="上个季度按零售区域按零售渠道零售额", reference_instant=REFERENCE)
    )
    assert first.status == "answered", first.message
    assert first.query_frame
    assert first.query_frame.group_by == ("retail_channel", "retail_region")
    answer = ask_data(
        db,
        AskRequest(
            question="那华南呢",
            conversation_id=first.conversation_id,
            reference_instant=REFERENCE,
        ),
    )
    assert answer.status == "answered", answer.message
    assert answer.query_frame
    assert answer.query_frame.group_by == ("retail_channel",)
    assert [item.value for item in answer.query_frame.slices] == ["华南"]


def test_time_followups_behind_a_continuation_equal_complete_questions(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """The continuation words never count as an unexplained modifier of the time phrase."""
    for followup, complete in (
        ("what about August 2026", "retail revenue in East China in August 2026"),
        ("what about 2026 Q3", "retail revenue in East China in 2026 Q3"),
        ("how about last month", "last month retail revenue in East China"),
        ("那2026年8月呢", "2026年8月华东零售额"),
    ):
        first = ask_data(
            db,
            AskRequest(
                question="last quarter retail revenue in East China", reference_instant=REFERENCE
            ),
        )
        answer = ask_data(
            db,
            AskRequest(
                question=followup,
                conversation_id=first.conversation_id,
                reference_instant=REFERENCE,
            ),
        )
        standalone = ask_data(db, AskRequest(question=complete, reference_instant=REFERENCE))
        assert answer.status == standalone.status == "answered", (followup, answer.message)
        assert answer.result == standalone.result
        assert answer.query_frame == standalone.query_frame


def test_dimension_value_followup_outranks_knowledge_routing(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A fully understood value edit answers with numbers instead of a lineage prompt."""
    first = ask_data(
        db,
        AskRequest(
            question="last quarter retail revenue in East China", reference_instant=REFERENCE
        ),
    )
    answer = ask_data(
        db,
        AskRequest(
            question="what about stores",
            conversation_id=first.conversation_id,
            reference_instant=REFERENCE,
        ),
    )
    assert answer.status == "answered", answer.message
    assert answer.knowledge is None
    assert answer.query_frame
    assert {(item.dimension_id, item.value) for item in answer.query_frame.slices} == {
        ("retail_channel", "门店"),
        ("retail_region", "华东"),
    }
    assert answer.result
    assert answer.result.rows


def test_unknown_followup_suffix_requires_clarification(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A known region does not authorize ignoring an unexplained new instruction."""
    first = ask_data(db, AskRequest(question="上个季度华东零售额", reference_instant=REFERENCE))
    answer = ask_data(
        db,
        AskRequest(
            question="那华南,魔法校正呢",
            conversation_id=first.conversation_id,
            reference_instant=REFERENCE,
        ),
    )
    assert answer.status == "clarification"
    assert answer.result is None
