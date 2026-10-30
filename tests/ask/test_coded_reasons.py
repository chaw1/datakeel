# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Refusals carry a reason code with its fragments; unsupported time words never run."""

from datetime import UTC, date, datetime
from typing import get_args

import pytest

from datakeel.ask import service
from datakeel.ask.reasons import chinese_message
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskReason, AskReasonCode, AskRequest, TimeRange
from datakeel.core.metric_models import CompiledQuery, QueryResult
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)

# Time words the parser recognizes as temporal but cannot turn into an interval.
_UNSUPPORTED_TIME = [
    ("上个世纪零售额", "上个世纪"),
    ("上世纪90年代零售额", "上世纪"),
    ("上世纪 90 年代的零售额", "上世纪"),
    ("去年同期零售额", "同期"),
    ("2019财年零售额", "财年"),
    ("Q5零售额", "Q5"),
    ("retail revenue last century", "century"),
    ("retail revenue in the nineties", "nineties"),
]
# Time words that do parse keep answering with the interval they name.
_SUPPORTED_TIME = [
    ("近18个月零售额", TimeRange(start=date(2025, 4, 1), end=date(2026, 10, 1))),
    ("近 18 个月的零售额", TimeRange(start=date(2025, 4, 1), end=date(2026, 10, 1))),
    ("去年零售额", TimeRange(start=date(2025, 1, 1), end=date(2026, 1, 1))),
    ("retail revenue last quarter", TimeRange(start=date(2026, 7, 1), end=date(2026, 10, 1))),
]


@pytest.fixture
def executed(monkeypatch: pytest.MonkeyPatch) -> list[CompiledQuery]:
    """Record every query the service runs instead of opening the source."""
    queries: list[CompiledQuery] = []

    def record(_url: str, query: CompiledQuery) -> QueryResult:
        queries.append(query)
        return QueryResult(columns=["value"], rows=[[1]])

    monkeypatch.setattr(service, "execute_query", record)
    return queries


def _ask(db: Database, question: str) -> AskAnswer:
    return ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))


def test_unsupported_time_words_refuse_with_a_coded_time_reason(
    db: Database, enterprise_sample: EnterpriseSample, executed: list[CompiledQuery]
) -> None:
    """Century, decade, same-period, fiscal and Q5 wording refuse instead of answering all time."""
    assert enterprise_sample.sources
    for question, fragment in _UNSUPPORTED_TIME:
        answer = _ask(db, question)
        assert answer.status == "unanswerable", question
        assert answer.result is None, question
        assert answer.reason is not None, question
        assert answer.reason.code == "time_not_understood", question
        assert any(fragment in item for item in answer.reason.fragments), answer.reason
        assert answer.message == chinese_message(answer.reason)
    assert executed == []


def test_time_words_that_parse_still_answer(
    db: Database, enterprise_sample: EnterpriseSample, executed: list[CompiledQuery]
) -> None:
    """Supported relative windows keep their interval and run exactly once each."""
    assert enterprise_sample.sources
    for question, expected in _SUPPORTED_TIME:
        answer = _ask(db, question)
        assert answer.status == "answered", (question, answer.message)
        assert answer.time_range == expected, question
        assert answer.reason is None
    assert len(executed) == len(_SUPPORTED_TIME)


@pytest.mark.parametrize(
    ("question", "code", "fragments", "message"),
    [
        (
            "average retail revenue in March 2026",
            "unsupported_calculation",
            ("average",),
            "登记指标不支持所问的计算: 「average」",
        ),
        (
            "retail revenue in Q5 2026",
            "time_not_understood",
            ("Q5",),
            "无法可靠解析时间条件: 未理解「Q5」",
        ),
        (
            "在上海的零售额",
            "unclear_condition",
            ("在上海的",),
            "请明确维度条件: 未理解「在上海的」",
        ),
    ],
)
def test_refusals_record_the_code_and_the_unchanged_chinese_message(
    db: Database,
    enterprise_sample: EnterpriseSample,
    question: str,
    code: str,
    fragments: tuple[str, ...],
    message: str,
) -> None:
    """The stored message stays the old Chinese wording; the code and fragments travel with it."""
    assert enterprise_sample.sources
    answer = _ask(db, question)
    assert answer.reason is not None
    assert (answer.reason.code, answer.reason.fragments) == (code, fragments)
    assert answer.message == message
    assert answer.model_dump(mode="json")["reason"]["code"] == code


def test_every_code_has_a_chinese_wording_and_old_answers_still_load() -> None:
    """Each code words itself; an answer stored before codes existed reads with no reason."""
    for code in get_args(AskReasonCode):
        assert chinese_message(AskReason(code=code, fragments=("x",), notes=("y",)))
    reason = AskReason(code="unclear_condition", fragments=("上海",), notes=("Region value",))
    assert chinese_message(reason) == "请明确维度条件: Region value; 未理解「上海」"
    stored = AskAnswer(
        session_id="s",
        question="q",
        status="unanswerable",
        message="登记指标不支持所问的计算: 「中位数」",
        reference_instant=REFERENCE,
    ).model_dump(mode="json")
    assert "reason" not in stored
    assert AskAnswer.model_validate(stored).reason is None
