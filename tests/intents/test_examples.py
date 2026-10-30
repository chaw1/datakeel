# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The three spec examples, clarification, overreach and resuming after a failed step."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions import service
from datakeel.core.intent_models import PageContext
from datakeel.intents.chains import advance_chain
from datakeel.storage.intent_reads import held_tasks
from tests.intents.support import REASSIGN, REWORK, SETUP, images, plan, run_to_end, team
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_reassign_sentence_takes_back_untouched_tasks_and_assigns_them(db: Database) -> None:
    """Release each of wang's untouched tasks, then assign the same tasks to li."""
    project, tasks = team(db)
    result = plan(db, REASSIGN, PageContext(project_id=project.id), actor="boss")
    assert result.kind == "plan", result.text
    assert result.chain is not None
    revoke, assign = result.chain.steps
    assert revoke.action == "revoke_assignment"
    assert sorted(str(item["task_id"]) for item in revoke.items) == sorted(
        [tasks[0].id, tasks[1].id]
    )
    assert assign.params["actor"] == "li"
    assert assign.params["strategy"] == "assign"
    assert held_tasks(db, "wang", project_id=project.id)
    finished = run_to_end(db, result.chain, "boss")
    assert finished.status == "succeeded"
    assert not held_tasks(db, "wang", project_id=project.id)
    assert {task for _, task in held_tasks(db, "li", project_id=project.id)} == {
        tasks[0].id,
        tasks[1].id,
    }


def test_rework_question_is_answered_directly_without_a_plan(db: Database) -> None:
    """A read question runs the read function at once and says it does not filter by week."""
    project, _ = team(db)
    result = plan(db, REWORK, PageContext(project_id=project.id), actor="boss")
    assert result.kind == "answer"
    assert result.answer is not None
    assert result.answer.function == "rework_rate"
    assert result.answer.arguments == {"project_id": project.id}
    assert result.chain is None
    assert "不按周" in result.text or "还没有审核" in result.text


def test_unknown_person_is_asked_with_candidates_and_the_reply_resumes(db: Database) -> None:
    """A name that matches nobody becomes a question; picking a candidate completes the plan."""
    project, _ = team(db)
    asked = plan(db, "把小王手里没动的任务分给小周", PageContext(project_id=project.id), "boss")
    assert asked.kind == "clarify"
    assert asked.clarification is not None
    assert asked.clarification.fields == ["actor"]
    assert {item.id for item in asked.clarification.candidates} >= {"li", "zhao"}
    reply = plan(db, "小赵", PageContext(project_id=project.id), "boss", pending=asked)
    assert reply.kind == "plan", reply.text
    assert reply.chain is not None
    assert reply.chain.steps[-1].params["actor"] == "zhao"
    assert reply.chain.text == "把小王手里没动的任务分给小周"


def test_missing_dataset_is_asked_instead_of_guessed(db: Database, tmp_path: Path) -> None:
    """With two datasets and no page context the planner asks which one."""
    images(db, tmp_path / "a", name="路口图 A")
    images(db, tmp_path / "b", name="路口图 B")
    result = plan(db, SETUP)
    assert result.kind == "clarify"
    assert result.clarification is not None
    assert "dataset_id" in result.clarification.fields
    assert service.list_runs(db) == []


def test_annotator_is_refused_at_planning_with_the_missing_scope(db: Database) -> None:
    """An annotator cannot create a project by sentence, exactly as by hand."""
    project, _ = team(db)
    dataset_context = PageContext(dataset_id=project.dataset_id)
    result = plan(db, SETUP, dataset_context, actor="wang")
    assert result.kind == "refuse"
    assert result.missing_scopes == ["production:manage"]
    assert "production:manage" in result.text
    assert result.chain is None


def test_failed_step_resumes_without_repeating_finished_targets(db: Database) -> None:
    """A disabled assignee fails the second step; after re-enabling, resume only assigns."""
    project, tasks = team(db)
    runner = ServiceRunner(db)
    chain = plan(db, REASSIGN, PageContext(project_id=project.id), actor="boss").chain
    assert chain is not None
    runner("manage_users", {"operation": "update", "user_id": "li", "status": "disabled"}, "boss")
    failed = advance_chain(db, chain.id, "boss")
    assert failed.status == "failed"
    assert [step.status for step in failed.steps] == ["succeeded", "failed"]
    assert failed.steps[1].error
    revokes = [run for run in service.list_runs(db) if run.action_type == "revoke_assignment"]
    assert len(revokes) == 2
    runner("manage_users", {"operation": "update", "user_id": "li", "status": "active"}, "boss")
    resumed = advance_chain(db, chain.id, "boss")
    assert resumed.status == "succeeded"
    again = [run for run in service.list_runs(db) if run.action_type == "revoke_assignment"]
    assert len(again) == 2
    assert {task for _, task in held_tasks(db, "li", project_id=project.id)} == {
        tasks[0].id,
        tasks[1].id,
    }
