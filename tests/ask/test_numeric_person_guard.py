# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Requested people outrank incidental metric rankings without erasing nominal dimensions."""

import pytest

from datakeel.ask import service
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database
from tests.ask.parsing_helpers import registered_question

_PERSON_QUESTIONS = (
    "Who owns the highest inventory_units?",
    "Which team is responsible for the largest inventory_units?",
    "Which teams consume the highest inventory_units?",
    "inventory_units最高值由谁维护?",
    "库存量最高值由谁维护?",
    "What is the total inventory_units and who owns it?",
    "inventory_units value is maintained by who?",
    "Who maintains Refund Amounts total and how much is it?",
    "Which owner is responsible for the minimum Retail Revenue?",
    "退款金额最高值的负责人是谁?",
)


@pytest.mark.parametrize("question", _PERSON_QUESTIONS)
def test_person_question_with_scalar_words_never_reaches_sql(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
) -> None:
    """The real service must resolve knowledge or refuse before even invoking the query adapter."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("An explicit person request reached metric SQL execution")

    monkeypatch.setattr(service, "execute_query", forbidden)
    answer = ask_data(db, AskRequest(question=question))
    assert answer.answer_kind == "knowledge"
    assert answer.sql is None
    assert answer.result is None


def test_person_ownership_cannot_be_overridden_by_ranking_or_value_requests(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Both ranking and mixed value-plus-person heads retain the mandatory knowledge boundary."""
    for question in _PERSON_QUESTIONS:
        answer = ask_data(db, AskRequest(question=question))
        assert answer.answer_kind == "knowledge", question
        assert answer.sql is None
        assert answer.result is None


@pytest.mark.parametrize(
    "question",
    [
        "What is the highest inventory_units for each team?",
        "What is the total inventory_units for people who manage stores?",
        "Show inventory_units by people who own stores",
        "What is inventory_units by owner?",
        "把库存量按负责人分组。",
        "按人员查看 inventory_units 的总额",
        "统计各团队负责的 inventory_units 总额",
        "What is the total inventory_units for teams whose stores are active?",
    ],
)
def test_nominal_people_filters_or_groups_keep_numeric_route(question: str) -> None:
    """Person nouns and relative pronouns inside dimensions do not ask who a person is."""
    subject = "库存量" if "库存量" in question else "inventory_units"
    assert registered_question(question, subject) is None


@pytest.mark.parametrize(
    "question",
    [
        "Which owner has the highest inventory_units?",
        "Who manages the region with the largest inventory_units?",
        "谁负责的库存量最高?",
    ],
)
def test_business_owner_rank_heads_preserve_existing_metric_route(question: str) -> None:
    """Ranking a business owner dimension differs from asking for a metric's catalog steward."""
    subject = "库存量" if "库存量" in question else "inventory_units"
    assert registered_question(question, subject) is None


def test_unregistered_business_ranking_cannot_execute_without_metric_evidence(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy unknown business ranking route stays a refusal without inventing a metric."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("An unregistered business ranking reached metric SQL execution")

    monkeypatch.setattr(service, "execute_query", forbidden)
    answer = ask_data(db, AskRequest(question="Who owns the top stores?"))
    assert answer.status == "unanswerable"
    assert answer.sql is None
    assert answer.result is None
