# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Any time, filter or grouping fragment the parsers did not consume prevents execution."""

from datetime import UTC, datetime

import pytest

from datakeel.ask import service
from datakeel.ask.consumption import leftover_fragments
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import CompiledQuery, QueryResult
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)

_TIME_FRAGMENTS = [
    ("retail revenue in Q5 2026", "Q5"),
    ("retail revenue in FY2026", "FY2026"),
    ("retail revenue for the fiscal year", "fiscal"),
    ("retail revenue last fortnight", "fortnight"),
    ("retail revenue in mid-March 2026", "mid"),
    ("retail revenue around March 2026", "around"),
    ("retail revenue before March 2026", "before"),
    ("retail revenue on weekends in 2026", "weekends"),
    ("retail revenue during the holidays", "holidays"),
    ("retail revenue in March of last year", "Multiple distinct"),
    ("财年零售额", "财年"),
    ("2026年3月之前的零售额", "之前"),
    ("2026年13月零售额", "Invalid time expression"),
    ("下个月零售额", "Future periods"),
]
_FILTER_FRAGMENTS = [
    ("retail revenue in Shanghai", "Shanghai"),
    ("retail revenue for the Mars region", "Mars"),
    ("retail revenue among premium members", "premium"),
    ("retail revenue excluding East China", "East China"),
    ("retail revenue in East China and South China", "retail_region"),
    ("How many orders were cancelled in March 2026?", "cancelled"),
    ("在上海的零售额", "上海"),
    ("来自直播渠道的零售额", "直播"),
    ("东北区零售额", "Region value"),
    ("除了华东以外的零售额", "华东"),
]
_GROUP_FRAGMENTS = [
    ("retail revenue per salesperson", "salesperson"),
    ("retail revenue by store manager", "store"),
    ("retail revenue for each East China", "East China"),
    ("refund amount per channel", "channel"),
    ("按省份统计零售额", "省份"),
    ("各省零售额", "各省"),
]
_CALCULATION_FRAGMENTS = [
    ("average retail revenue in March 2026", "average"),
    ("retail revenue growth last quarter", "growth"),
    ("零售额同比", "同比"),
    ("highest retail revenue", "highest"),
    ("零售额最高", "最高"),
]


@pytest.fixture
def no_execution(monkeypatch: pytest.MonkeyPatch) -> list[CompiledQuery]:
    """Record every query the service tries to execute."""
    executed: list[CompiledQuery] = []

    def record(_url: str, query: CompiledQuery) -> QueryResult:
        executed.append(query)
        return QueryResult(columns=["value"], rows=[[1]])

    monkeypatch.setattr(service, "execute_query", record)
    return executed


@pytest.mark.parametrize(
    ("question", "fragment"),
    [*_TIME_FRAGMENTS, *_FILTER_FRAGMENTS, *_GROUP_FRAGMENTS, *_CALCULATION_FRAGMENTS],
)
def test_unconsumed_fragments_never_execute_or_return_numbers(
    db: Database,
    enterprise_sample: EnterpriseSample,
    no_execution: list[CompiledQuery],
    question: str,
    fragment: str,
) -> None:
    """Each category of unparsed fragment refuses before any SQL runs and names the fragment."""
    assert enterprise_sample.sources
    answer = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
    assert answer.status in {"clarification", "unanswerable"}, question
    assert no_execution == []
    assert answer.result is None
    assert answer.sql is None
    assert fragment in answer.message, answer.message


@pytest.mark.parametrize(("question", "fragment"), _TIME_FRAGMENTS[:9])
def test_time_fragments_refuse_as_time(
    db: Database, enterprise_sample: EnterpriseSample, question: str, fragment: str
) -> None:
    """Unparsed time words are reported as time problems, not silently dropped as filters."""
    assert enterprise_sample.sources
    answer = ask_data(db, AskRequest(question=question, reference_instant=REFERENCE))
    assert answer.status == "unanswerable"
    assert answer.message.startswith("无法可靠解析时间条件")
    assert answer.interpretation is not None
    assert any(fragment in item for item in answer.interpretation.unconsumed)


def test_interpretation_records_what_an_answer_used(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Answers expose metric, interval, basis, slices, groups and an empty leftover list."""
    assert enterprise_sample.sources
    answer = ask_data(
        db,
        AskRequest(
            question="online retail revenue by region last quarter", reference_instant=REFERENCE
        ),
    )
    assert answer.status == "answered"
    interpretation = answer.interpretation
    assert interpretation is not None
    assert interpretation.metric_id == "retail_revenue"
    assert interpretation.time_range is not None
    assert interpretation.time_range.start.isoformat() == "2026-07-01"
    assert interpretation.time_basis == "period"
    assert [(item.dimension_id, item.value) for item in interpretation.slices] == [
        ("retail_channel", "线上")
    ]
    assert interpretation.group_by == ("retail_region",)
    assert interpretation.unconsumed == ()
    assert "interpretation" in answer.model_dump(mode="json")


def test_refusals_keep_the_partial_interpretation(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A refusal shows what was understood and which fragment blocked the answer."""
    assert enterprise_sample.sources
    answer = ask_data(
        db,
        AskRequest(question="retail revenue in Shanghai last month", reference_instant=REFERENCE),
    )
    assert answer.status == "clarification"
    assert answer.interpretation is not None
    assert answer.interpretation.time_range is not None
    assert "Shanghai" in " ".join(answer.interpretation.unconsumed)


def test_leftovers_distinguish_time_condition_calculation_and_ranking() -> None:
    """The consumption check classifies each kind of leftover independently."""
    question = "average revenue in Mars for FY2026 top"
    leftovers = leftover_fragments(question, [(8, 15)])
    assert "FY2026" in leftovers.times
    assert any("Mars" in item for item in leftovers.conditions)
    assert leftovers.calculations == ("average",)
    assert leftovers.rankings == ("top",)


def test_modifiers_next_to_a_resolved_period_are_leftovers() -> None:
    """A word that changes a parsed interval keeps that interval from being used as is."""
    question = "revenue before March 2026"
    span = (question.index("March"), len(question))
    assert leftover_fragments(question, [span], (span,)).times == ("before",)
    chinese = "2026年3月以后的收入"
    period = (0, chinese.index("以后"))
    assert leftover_fragments(chinese, [period], (period,)).times == ("以后",)
    assert leftover_fragments("revenue in March 2026", [(8, 21)], ((8, 21),)).times == ()
