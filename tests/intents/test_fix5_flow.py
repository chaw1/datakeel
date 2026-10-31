# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX5: the flow checks what the model left open before a sentence ends.

Every sentence here is written for the FIX3 development world (North Crossing, 南区车道);
none comes from a regression or blind set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from tests.intents.fix3_support import planned, steps, two_projects
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _none(**fields: object) -> dict[str, object]:
    return {"kind": "none", "reason": "recorded", **fields}


def test_an_action_that_fits_but_misses_a_value_is_asked_with_choices(db: Database) -> None:
    """A "none" naming the action that does it becomes that action's question (11.2-1)."""
    two_projects(db)
    fits = _none(related=["publish_label_set", "create_label_set"], fits="publish_label_set")
    asked = planned(db, "把那套标签定下来", [fits], PageContext())
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    assert asked.clarification.candidates, asked.text
    assert "平台没有" not in asked.text
    # A single name in "choose" is no choice: the words fit that action.
    single = _none(choose=["publish_label_set"], related=["publish_label_set"])
    alone = planned(db, "Publish that label set", [single], PageContext())
    assert alone.kind == "clarify", alone.text
    assert alone.clarification is not None
    assert alone.clarification.candidates


def test_an_action_that_fits_but_the_speaker_may_not_run_is_refused(db: Database) -> None:
    """The registered action exists, the speaker lacks its permission: a refusal, why."""
    _, south, _ = two_projects(db)
    fits = _none(
        related=["upgrade_project"],
        fits="upgrade_project",
        steps=[{"id": "s1", "action": "upgrade_project", "params": {"project_id": south.id}}],
    )
    refused = planned(db, "南区车道换成团队档吧", [fits], PageContext(), actor="wang")
    assert refused.kind == "refuse", refused.text
    assert refused.missing_scopes


def test_only_a_request_nothing_registered_does_is_said_missing(db: Database) -> None:
    """No fitting action (or one the registry lacks): the feature is missing, never a question."""
    two_projects(db)
    close = _none(related=["configure_project"])
    missing = planned(db, "给南区车道定个交付截止日", [close], PageContext())
    assert missing.kind == "unsupported", missing.text
    assert "平台没有这个功能" in missing.text
    invented = _none(related=["configure_project"], fits="set_deadline")
    still = planned(db, "Give 南区车道 a delivery deadline", [invented], PageContext())
    assert still.kind == "unsupported", still.text
    assert "平台没有这个功能" in still.text


def test_a_change_that_is_already_so_names_the_current_state(db: Database) -> None:
    """Already disabled, already with that reviewer, never quarantined: said, no card (11.2-4)."""
    _, south, _ = two_projects(db)
    disable = {"operation": "update", "user_id": "li", "status": "disabled"}
    ServiceRunner(db)("manage_users", disable, "boss")
    off = ("manage_users", disable)
    account = planned(db, "小李这个号关掉", [steps(off)], PageContext())
    assert account.kind == "answer", account.text
    assert "小李" in account.text
    assert "已停用" in account.text
    review = {"task_ids": {"$tasks": {"numbers": [3]}}, "actor": "zhao", "stage": "review"}
    page = PageContext(project_id=south.id)
    held = planned(db, "#3 让小赵来审", [steps(("assign_tasks", review))], page)
    assert held.kind == "answer", held.text
    assert "小赵手上审核" in held.text
    files = {"selection": {"$files": {"kind": "named", "names": ["1.png"]}}}
    data = PageContext(dataset_id=south.dataset_id)
    free = planned(db, "1.png 解除隔离", [steps(("unquarantine_files", files))], data)
    assert free.kind == "answer", free.text
    assert "本来就没被隔离" in free.text
