# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A reclaimed rework round can be handed to someone else by name; separation still holds."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.production_parameters import AssignTasksParams
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.models import new_id
from datakeel.core.production_models import Assignment
from datakeel.core.workbench_models import SkillDispatchPreviewRequest
from datakeel.storage.production_assignments import assign_tasks
from datakeel.storage.production_queries import get_task, list_assignments, list_tasks
from datakeel.storage.workbench_samples import dispatch_preview
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, failure, review, save, submit
from tests.production_team_support import ServiceRunner, grant_skills, register

if TYPE_CHECKING:
    from datakeel.core.models import JsonDocument
    from datakeel.core.production_models import WorkflowTier
    from datakeel.storage.database import Database

REQUIREMENT = {"annotation_type": "classification", "domain": "retail", "min_level": 1}
PEOPLE = {"ann-a": "annotator", "ann-b": "annotator", "rev": "reviewer", "pm": "project_manager"}


def _caller(actor: str) -> AccessContext:
    return AccessContext(actor=actor, entry="ask", scope="query")


def _returned_rework(db: Database, tier: WorkflowTier = "team") -> tuple[ServiceRunner, str, str]:
    """Annotator A submits, a reviewer returns it: round 1, still held by A."""
    project, _tasks = production_fixture(db, tier, count=2)
    runner = ServiceRunner(db)
    register(runner, project.id, PEOPLE)
    task = claim(db, project.id, "ann-a")
    save(db, task.id, "ann-a")
    submit(db, task.id, "ann-a")
    claim(db, project.id, "rev", "review")
    review(db, task.id, "rev", approve=False)
    returned = get_task(db, task.id)
    assert (returned.state, returned.round, returned.annotator_id) == ("pending", 1, "ann-a")
    return runner, project.id, task.id


def _active(db: Database, task_id: str) -> list[Assignment]:
    return [item for item in list_assignments(db, task_id) if item.active]


def _assignments(details: JsonDocument) -> list[Assignment]:
    values = details.root["assignments"]
    assert isinstance(values, list)
    return [Assignment.model_validate(item) for item in values]


@pytest.mark.parametrize("tier", ["group", "team"])
def test_reclaimed_rework_is_handed_over_by_name_and_the_plan_says_so(
    db: Database, tier: WorkflowTier
) -> None:
    """The plan names A to B; afterwards B holds this round, opens it and submits it."""
    runner, _project_id, task_id = _returned_rework(db, tier)
    held = failure(lambda: runner("assign_tasks", {"task_ids": [task_id], "actor": "ann-b"}, "pm"))
    assert isinstance(held, ConflictError), held
    runner("revoke_assignment", {"task_id": task_id, "reason": "A is away"}, "pm")
    plan = runner.plan(
        "assign_tasks",
        {
            "task_ids": [task_id],
            "actor": "ann-b",
            "transfers": [
                {"task_id": task_id, "round": 1, "from_actor": "pm", "to_actor": "ann-b"}
            ],
        },
        "pm",
    )
    assert plan.canonical_params["transfers"] == [
        {"task_id": task_id, "round": 1, "from_actor": "ann-a", "to_actor": "ann-b"}
    ]
    handed = failure(
        lambda: runner("assign_tasks", {"task_ids": [task_id], "actor": "ann-b"}, "pm")
    )
    assert handed is None, handed
    (assignment,) = _active(db, task_id)
    assert (assignment.actor, assignment.transferred_from) == ("ann-b", "ann-a")
    assert get_task(db, task_id).annotator_id == "ann-b"
    save(db, task_id, "ann-b")
    finished = submit(db, task_id, "ann-b")
    assert (finished.state, finished.round, finished.annotator_id) == ("submitted", 1, "ann-b")


def test_neither_the_original_nor_the_new_annotator_can_review_the_handed_over_task(
    db: Database,
) -> None:
    """In the team tier A and B are both annotators of the task; only someone else reviews."""
    runner, project_id, task_id = _returned_rework(db)
    runner("revoke_assignment", {"task_id": task_id, "reason": "A is away"}, "pm")
    runner("assign_tasks", {"task_ids": [task_id], "actor": "ann-b"}, "pm")
    save(db, task_id, "ann-b")
    submit(db, task_id, "ann-b")
    for person in ("ann-a", "ann-b"):
        # Both may review in general, so only separation of duties can keep them out here.
        runner(
            "manage_users",
            {
                "operation": "bind_role",
                "user_id": person,
                "role_id": "reviewer",
                "project_id": project_id,
            },
        )
    for person in ("ann-a", "ann-b"):
        queue = failure(lambda person=person: claim(db, project_id, person, "review"))
        assert isinstance(queue, NotFoundError), queue
        named = failure(
            lambda person=person: runner(
                "assign_tasks", {"task_ids": [task_id], "actor": person, "stage": "review"}, "pm"
            )
        )
        assert isinstance(named, AuthorizationError), named
        assert "Separation of duties" in str(named)
        decided = failure(lambda person=person: review(db, task_id, person))
        assert isinstance(decided, AuthorizationError), decided
    claim(db, project_id, "rev", "review")
    review(db, task_id, "rev")
    assert get_task(db, task_id).state == "approved"


def test_a_plan_whose_handover_changed_is_refused(db: Database) -> None:
    """Executing an assignment that does not declare the current handover is a conflict."""
    runner, _project_id, task_id = _returned_rework(db)
    runner("revoke_assignment", {"task_id": task_id, "reason": "A is away"}, "pm")
    with db.session() as session:
        db.lock_writes(session)
        refused = failure(
            lambda: assign_tasks(
                session,
                AssignTasksParams(request_id=new_id(), task_ids=(task_id,), actor="ann-b"),
            )
        )
        session.rollback()
    assert isinstance(refused, ConflictError), refused
    assert "rework handover" in str(refused)
    assert get_task(db, task_id).annotator_id == "ann-a"
    assert _active(db, task_id) == []


def test_claims_never_take_someone_elses_rework(db: Database) -> None:
    """Self-claim keeps rework with its original annotator, held or reclaimed."""
    runner, project_id, task_id = _returned_rework(db)
    runner("revoke_assignment", {"task_id": task_id, "reason": "A is away"}, "pm")
    taken = claim(db, project_id, "ann-b")
    assert taken.id != task_id
    again = claim(db, project_id, "ann-a")
    assert (again.id, again.annotator_id) == (task_id, "ann-a")


def _skill_rework(db: Database) -> tuple[ServiceRunner, str, str]:
    runner, project_id, task_id = _returned_rework(db)
    grant_skills(runner, {"ann-a": 1, "ann-b": 1})
    runner(
        "configure_project",
        {"project_id": project_id, "skill_requirement": REQUIREMENT},
        "pm",
    )
    runner("revoke_assignment", {"task_id": task_id, "reason": "Redispatch"}, "pm")
    return runner, project_id, task_id


def test_skill_dispatch_returns_rework_to_an_original_annotator_in_service(db: Database) -> None:
    """B has less load, but the rework round still goes back to A while A is active."""
    runner, project_id, task_id = _skill_rework(db)
    other = next(task.id for task in list_tasks(db, project_id) if task.id != task_id)
    runner("assign_tasks", {"task_ids": [other], "actor": "ann-a"}, "pm")
    preview = dispatch_preview(
        db, project_id, _caller("pm"), SkillDispatchPreviewRequest(task_ids=(task_id,))
    )
    assert [(pick.actor, pick.transferred_from) for pick in preview.picks] == [("ann-a", None)]
    details = runner("assign_tasks", {"task_ids": [task_id], "strategy": "skill"}, "pm")
    (assignment,) = _assignments(details)
    assert (assignment.actor, assignment.transferred_from) == ("ann-a", None)
    assert get_task(db, task_id).annotator_id == "ann-a"


def test_skill_dispatch_hands_rework_over_once_the_original_annotator_is_deactivated(
    db: Database,
) -> None:
    """With A disabled the least-loaded qualified person takes the round, recorded as from A."""
    runner, project_id, task_id = _skill_rework(db)
    runner("manage_users", {"operation": "update", "user_id": "ann-a", "status": "disabled"})
    preview = dispatch_preview(
        db, project_id, _caller("pm"), SkillDispatchPreviewRequest(task_ids=(task_id,))
    )
    assert [(pick.actor, pick.transferred_from) for pick in preview.picks] == [("ann-b", "ann-a")]
    details = runner("assign_tasks", {"task_ids": [task_id], "strategy": "skill"}, "pm")
    (assignment,) = _assignments(details)
    assert (assignment.actor, assignment.transferred_from) == ("ann-b", "ann-a")
    task = get_task(db, task_id)
    assert (task.annotator_id, task.round) == ("ann-b", 1)
    save(db, task_id, "ann-b")
    assert submit(db, task_id, "ann-b").state == "submitted"
