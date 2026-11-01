# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Self-claims are checked against dispatch, workload and review-separation rules before a card."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.storage.production_queries import get_task
from tests.intents.planning_support import planned, steps, two_projects
from tests.intents.support import run_to_end
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
    assert result.chain is not None
    finished = run_to_end(db, result.chain, "wang")
    assert finished.status == "succeeded", finished


def test_two_claims_at_limit_one_are_refused_before_the_second_card(db: Database) -> None:
    """The first planned claim consumes capacity, and a legal single claim still executes."""
    _, south, _ = two_projects(db)
    ServiceRunner(db)("configure_project", {"project_id": south.id, "max_active_tasks": 1}, "boss")
    claim: tuple[str, dict[str, object]] = ("claim_task", {"project_id": south.id})
    context = PageContext(project_id=south.id)
    refused = planned(db, "连续领取两个任务", [steps(claim, claim)], context, actor="li")
    assert refused.chain is not None
    assert len(refused.chain.steps) == 1
    assert "最多 1 条" in refused.text, refused.text
    allowed = planned(db, "领取一个任务", [steps(claim)], context, actor="li")
    assert allowed.kind == "plan", allowed.text
    assert allowed.chain is not None
    finished = run_to_end(db, allowed.chain, "li")
    assert finished.status == "succeeded", finished


def test_an_earlier_named_dispatch_counts_toward_a_later_claim(db: Database) -> None:
    """A task dispatched to the speaker earlier in the plan also consumes their one open slot."""
    _, south, tasks = two_projects(db)
    ServiceRunner(db)("configure_project", {"project_id": south.id, "max_active_tasks": 1}, "boss")
    answer = steps(
        ("assign_tasks", {"task_ids": [tasks[4]], "actor": "boss"}),
        ("claim_task", {"project_id": south.id}),
    )
    result = planned(
        db, "先派给老板再让他领取", [answer], PageContext(project_id=south.id), actor="boss"
    )
    assert result.chain is not None
    assert len(result.chain.steps) == 1
    assert "最多 1 条" in result.text, result.text


def test_an_earlier_claim_consumes_the_last_free_task(db: Database) -> None:
    """Without a load limit, two claims still cannot both take the one remaining free task."""
    _, south, tasks = two_projects(db)
    ServiceRunner(db)("assign_tasks", {"task_ids": [tasks[5]], "actor": "wang"}, "boss")
    claim: tuple[str, dict[str, object]] = ("claim_task", {"project_id": south.id})
    result = planned(
        db,
        "连续领取两个任务",
        [steps(claim, claim)],
        PageContext(project_id=south.id),
        actor="li",
    )
    assert result.chain is not None
    assert len(result.chain.steps) == 1
    assert "没有可领的任务" in result.text, result.text


def test_upgrade_preserves_assign_only_strategy_and_a_legal_upgrade_executes(
    db: Database,
) -> None:
    """The effective upgraded tier refuses assign-only claims; a claim-strategy upgrade runs."""
    north, _, _ = two_projects(db)
    run = ServiceRunner(db)
    run("configure_project", {"project_id": north.id, "dispatch_strategy": "assign"}, "boss")
    answer = steps(
        ("upgrade_project", {"project_id": north.id, "workflow_tier": "team"}),
        ("claim_task", {"project_id": north.id}),
    )
    context = PageContext(project_id=north.id)
    refused = planned(db, "升级团队再领取", [answer], context, actor="boss")
    assert refused.chain is not None
    assert len(refused.chain.steps) == 1
    assert "只能由负责人派单" in refused.text, refused.text
    run("configure_project", {"project_id": north.id, "dispatch_strategy": "claim"}, "boss")
    allowed = planned(db, "升级团队再领取", [answer], context, actor="boss")
    assert allowed.kind == "plan", allowed.text
    assert allowed.chain is not None
    finished = run_to_end(db, allowed.chain, "boss")
    assert finished.status == "succeeded", finished
