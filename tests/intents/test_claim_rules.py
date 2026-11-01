# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Self-claims are checked against dispatch, workload and review-separation rules before a card."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.storage.production_queries import get_task
from tests.intents.fix3_support import planned, steps, two_projects
from tests.production_team_ops import review, save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _claim(db: Database, project_id: str, actor: str, stage: str = "annotation") -> IntentResult:
    values: dict[str, object] = {"project_id": project_id, "stage": stage}
    return planned(
        db,
        "领一个南区车道的任务" if stage == "annotation" else "领一个南区车道的审核任务",
        [steps(("claim_task", values))],
        PageContext(),
        actor=actor,
    )


def _reviewer(db: Database, project_id: str, person: str) -> None:
    ServiceRunner(db)(
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": person,
            "role_id": "reviewer",
            "project_id": project_id,
        },
        "boss",
    )


def test_review_claims_skip_everyone_who_annotated_even_after_a_handover(db: Database) -> None:
    """A submitted rework task is not offered to its original or replacement annotator."""
    _, south, tasks = two_projects(db)
    run, task = ServiceRunner(db), tasks[2]
    review(db, task, "zhao", approve=False)
    run("revoke_assignment", {"task_id": task, "reason": "转给小王返工"}, "boss")
    run("assign_tasks", {"task_ids": [task], "actor": "wang"}, "boss")
    save(db, task, "wang")
    submit(db, task, "wang")
    assert get_task(db, task).annotator_id == "wang"
    for person, name in (("li", "小李"), ("wang", "小王")):
        _reviewer(db, south.id, person)
        refused = _claim(db, south.id, person, "review")
        assert refused.kind != "plan", refused.text
        assert all(word in refused.text for word in (name, "标过", "换一个审核人")), refused.text
    allowed = _claim(db, south.id, "zhao", "review")
    assert allowed.kind == "plan", allowed.text


def test_a_team_claim_at_the_person_limit_is_refused_but_another_person_can_claim(
    db: Database,
) -> None:
    """The current actor's open annotation load plus this one claim must fit the limit."""
    _, south, _ = two_projects(db)
    ServiceRunner(db)("configure_project", {"project_id": south.id, "max_active_tasks": 2}, "boss")
    over = _claim(db, south.id, "wang")
    assert over.kind != "plan", over.text
    assert all(word in over.text for word in ("小王", "2 条在做", "最多 2 条")), over.text
    fits = _claim(db, south.id, "li")
    assert fits.kind == "plan", fits.text


def test_manager_assigned_projects_do_not_offer_self_claim(db: Database) -> None:
    """Assign-only annotation is routed to a manager; an ordinary self-claim still plans."""
    _, south, _ = two_projects(db)
    run = ServiceRunner(db)
    run("configure_project", {"project_id": south.id, "dispatch_strategy": "assign"}, "boss")
    refused = _claim(db, south.id, "li")
    assert refused.kind != "plan", refused.text
    assert all(word in refused.text for word in ("只能由负责人派单", "派给你")), refused.text
    run("configure_project", {"project_id": south.id, "dispatch_strategy": "claim"}, "boss")
    allowed = _claim(db, south.id, "li")
    assert allowed.kind == "plan", allowed.text


def test_an_earlier_release_is_applied_before_the_claim_is_checked(db: Database) -> None:
    """A prior release makes room and frees a task, so stale state does not block the chain."""
    _, south, tasks = two_projects(db)
    ServiceRunner(db)("configure_project", {"project_id": south.id, "max_active_tasks": 2}, "boss")
    answer = steps(
        ("release_task", {"task_id": tasks[0]}),
        ("claim_task", {"project_id": south.id}),
    )
    result = planned(db, "先放弃南区车道第一条再领一个", [answer], PageContext(), actor="wang")
    assert result.kind == "plan", result.text
