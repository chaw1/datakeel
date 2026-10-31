# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX6: one task group across the steps of a plan, and the next segment of a list."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.core.models import AssetRef
from datakeel.intents import selectors
from tests.intents.fix3_support import SOUTH, planned, steps, targets, two_projects
from tests.production_team_ops import save

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def test_the_next_two_are_counted_after_the_first_two(db: Database) -> None:
    """The next two are counted after the first two."""
    _, _, tasks = two_projects(db)
    first = {"$tasks": {"project": SOUTH, "first": 1}}
    result = planned(
        db,
        "南区车道第一条派给小李, 接下来一条派给小赵",
        [
            steps(
                ("assign_tasks", {"task_ids": first, "actor": "小李"}),
                ("assign_tasks", {"task_ids": first, "actor": "小赵"}),
            )
        ],
        PageContext(),
    )
    assert targets(result, 0) == tasks[0:1]
    assert targets(result, 1) == tasks[1:2]


def test_the_same_first_n_without_next_words_is_the_same_tasks(db: Database) -> None:
    """The same first n without next words is the same tasks."""
    _, _, tasks = two_projects(db)
    first = {"$tasks": {"project": SOUTH, "first": 1}}
    result = planned(
        db,
        "Release the first task of 南区车道 and give it to 小李",
        [
            steps(
                ("revoke_assignment", {"task_id": first, "reason": "reassign"}),
                ("assign_tasks", {"task_ids": first, "actor": "小李"}),
            )
        ],
        PageContext(),
    )
    assert targets(result, 0) == targets(result, 1) == tasks[0:1]


def test_revoke_then_reassign_acts_on_one_set_and_protection_spares_both(db: Database) -> None:
    """Saved work is spared by both steps; "都收回再全派" moves the same tasks, saved ones too."""
    _, _, tasks = two_projects(db)
    save(db, tasks[0], "wang")  # saved work: taking it back is protected unless said
    held = {"$tasks": {"project": SOUTH, "holder": "小王"}}
    for said, moved in (
        ("把南区车道小王手上的任务收回, 再派给小李", tasks[1:2]),
        ("把南区车道小王手上的都收回, 再全部派给小李", tasks[0:2]),
    ):
        result = planned(
            db,
            said,
            [
                steps(
                    ("revoke_assignment", {"task_id": held, "reason": "改派"}),
                    ("assign_tasks", {"task_ids": held, "actor": "小李"}),
                )
            ],
            PageContext(),
        )
        assert targets(result, 0) == moved
        assert targets(result, 1) == moved


def test_each_groups_first_file_is_the_one_the_list_shows_first(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each groups first file is the one the list shows first."""
    shown = ["c", "a", "b", "d"]
    pairs = [("a", "b"), ("a", "c")]
    found = [
        SimpleNamespace(
            predicate="near_duplicate_of",
            status="candidate",
            subject=AssetRef(asset_id=left),
            object=AssetRef(asset_id=right),
        )
        for left, right in pairs
    ]
    monkeypatch.setattr(selectors, "_dataset_files", lambda *_args: shown)
    monkeypatch.setattr(selectors, "list_assertions", lambda _db: found)
    # c is first in the list, so the group a-b-c keeps c; the copies come in list order.
    assert selectors.near_duplicates(db, "set", None) == ["a", "b"]


def test_a_project_named_once_scopes_every_step_of_the_chain(db: Database) -> None:
    """「在南区车道里」 said once holds for the second step's tasks too."""
    _, _, tasks = two_projects(db)
    result = planned(
        db,
        "在南区车道里, 先把第五条派给小李, 再把第六条派给小赵",
        [
            steps(
                (
                    "assign_tasks",
                    {"task_ids": {"$tasks": {"project": SOUTH, "numbers": [5]}}, "actor": "小李"},
                ),
                ("assign_tasks", {"task_ids": {"$tasks": {"numbers": [6]}}, "actor": "小赵"}),
            )
        ],
        PageContext(),
    )
    assert targets(result, 0) == tasks[4:5]
    assert targets(result, 1) == tasks[5:6]


def test_one_action_given_the_same_first_one_twice_takes_the_next(db: Database) -> None:
    """Two people each given "the first unclaimed one" get two different tasks."""
    _, _, tasks = two_projects(db)
    first = {"$tasks": {"project": SOUTH, "holder": "nobody", "first": 1}}
    result = planned(
        db,
        "把南区车道没人领的派一条给小李, 再派一条给小赵",
        [
            steps(
                ("assign_tasks", {"task_ids": first, "actor": "小李"}),
                ("assign_tasks", {"task_ids": first, "actor": "小赵"}),
            )
        ],
        PageContext(),
    )
    assert targets(result, 0) == tasks[4:5]
    assert targets(result, 1) == tasks[5:6]


def test_a_later_step_of_the_same_group_keeps_what_only_it_can_take(db: Database) -> None:
    """Take back the untouched ones that are held, then give every untouched one to 小李."""
    _, _, tasks = two_projects(db)
    untouched = {"$tasks": {"project": SOUTH, "untouched": True}}
    result = planned(
        db,
        "Give 小李 every task in 南区车道 that has no annotation yet",
        [
            steps(
                ("revoke_assignment", {"task_id": untouched, "reason": "reassign"}),
                ("assign_tasks", {"task_ids": untouched, "actor": "小李"}),
            )
        ],
        PageContext(),
    )
    assert targets(result, 0) == tasks[0:2]
    assert set(targets(result, 1)) == {*tasks[0:2], *tasks[4:6]}
