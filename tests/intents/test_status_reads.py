# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A question about how things stand is answered, never planned as a change."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.intent_models import PageContext
from datakeel.intents.readonly import status_question
from tests.intents.planning_support import SOUTH, planned, steps, two_projects

if TYPE_CHECKING:
    from datakeel.storage.database import Database

ASKED = (
    "南区车道定稿了吗?",
    "小李手上的第三条提交了没有",
    "第三条是不是已经提交了",
    "Has 南区车道 been finalized?",
    "Did Li hand in the third task?",
)
TOLD = (
    "把南区车道定稿",
    "能把第五条派给小王吗?",
    "南区车道定稿了吗? 没有的话帮我定稿",
    "Can you finalize 南区车道?",
    "Is it possible to split 南区车道 again?",
)


@pytest.mark.parametrize("text", ASKED)
def test_status_questions_are_recognized(text: str) -> None:
    """Status questions are recognized."""
    assert status_question(text)


@pytest.mark.parametrize(
    "text", TOLD, ids=["told", "can-you-zh", "else-do-it", "can-you", "is-it-possible"]
)
def test_requests_are_never_taken_for_questions(text: str) -> None:
    """Requests are never taken for questions."""
    assert not status_question(text)


@pytest.mark.parametrize(
    ("text", "step", "read"),
    [
        ("南区车道定稿了吗?", ("finalize_project", {"project_id": SOUTH}), {"project_progress"}),
        (
            "南区车道第三条提交了没有?",
            ("submit_task", {"task_id": {"$tasks": {"project": SOUTH, "numbers": [3]}}}),
            {"get_task", "production_objects"},
        ),
        (
            "Has the first package of 南区车道 been accepted?",
            ("accept_package", {"project_id": SOUTH, "package_id": {"$nth": 1}}),
            {"package_status", "package_acceptance"},
        ),
    ],
)
def test_a_write_proposed_for_a_status_question_becomes_a_read(
    db: Database, text: str, step: tuple[str, dict[str, object]], read: set[str]
) -> None:
    """A write proposed for a status question becomes a read."""
    two_projects(db)
    result = planned(db, text, [steps(step)], PageContext())
    assert result.kind != "plan", result.text
    assert result.chain is None
    assert result.answer is not None, result.text
    assert result.answer.function in read


def test_a_write_proposed_for_status_finalize_becomes_a_read(db: Database) -> None:
    """「定稿了吗?」 with a finalize proposed reads the project's progress."""
    two_projects(db)
    proposed = steps(("finalize_project", {"project_id": SOUTH}))
    result = planned(db, "南区车道定稿了吗?", [proposed], PageContext())
    assert result.chain is None
    assert result.answer is not None, result.text
    assert result.answer.function == "project_progress"


def test_a_request_with_a_question_mark_still_plans(db: Database) -> None:
    """A request with a question mark still plans."""
    _, south, _ = two_projects(db)
    result = planned(
        db,
        "能把南区车道切成包吗?",
        [steps(("split_packages", {"project_id": south.name}))],
        PageContext(),
    )
    # Asked as a request, it is checked as the change: the reason it cannot run, no read.
    assert result.answer is None
    assert "切过包" in result.text


def test_a_change_asked_beside_a_question_still_plans(db: Database) -> None:
    """「第 3 条通过; 另外还有没有等我审的」: the review is planned, the question read."""
    _, _, tasks = two_projects(db)
    review = ("review_task", {"task_id": tasks[2], "decision": "approve"})
    waiting = ("production_objects", {"kind": "production_task", "project_id": SOUTH})
    result = planned(
        db,
        "南区车道第 3 条通过; 另外还有没有等我审的?",
        [steps(review, waiting)],
        PageContext(),
        "zhao",
    )
    assert result.chain is not None, result.text
    assert [step.action for step in result.chain.steps] == ["review_task"]
