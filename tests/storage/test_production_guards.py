# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production ownership, state transitions and mixed-project authorization fail closed."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ClaimTaskParams,
    ReleaseTaskParams,
    ReviewTaskParams,
    SaveRevisionParams,
    SplitPackagesParams,
    SubmitTaskParams,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.identity_models import User
from datakeel.core.models import new_id
from datakeel.storage.identity_rows import RoleBindingRow, UserRow
from datakeel.storage.production_assignments import (
    assign_tasks,
    claim_task,
    create_assignment,
    release_task,
)
from datakeel.storage.production_projects import split_packages
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    list_projects,
    next_task,
    project_for_params,
    project_progress,
)
from datakeel.storage.production_reviews import review_task, submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from tests.production_helpers import production_fixture
from tests.storage.test_production_workflow import save

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@pytest.mark.parametrize("personal_operation", ["assign", "claim", "review"])
def test_personal_rejects_assignment_and_human_review_records(
    db: Database,
    personal_operation: str,
) -> None:
    """The personal workflow cannot create assignment or review objects by an alternate path."""
    project, tasks = production_fixture(db)
    with db.session() as session:
        if personal_operation == "assign":
            with pytest.raises(ValidationError):
                create_assignment(session, require_task(session, tasks[0].id), "a", "annotation")
        elif personal_operation == "claim":
            with pytest.raises(ValidationError):
                claim_task(session, ClaimTaskParams(request_id="claim", project_id=project.id), "a")
        else:
            with pytest.raises(ValidationError):
                review_task(
                    session,
                    ReviewTaskParams(
                        request_id="review",
                        task_id=tasks[0].id,
                        revision_id="missing",
                        decision="approve",
                    ),
                    "a",
                )


def test_unknown_and_cross_project_targets_never_fall_back_to_global_scope(db: Database) -> None:
    """Resolving authorization from indirect targets requires every identifier to agree."""
    project, tasks = production_fixture(db)
    other, other_tasks = production_fixture(db)
    with db.session() as session:
        assert project_for_params(session, {"project_id": project.id}) == project.id
        assert project_for_params(session, {"task_id": tasks[0].id}) == project.id
        assert project_for_params(session, {"package_id": tasks[0].package_id}) == project.id
        params = AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="a")
        assert project_for_params(session, params) == project.id
        assert project_for_params(session, {"request_id": "read"}) is None
        with pytest.raises(NotFoundError):
            project_for_params(session, {"task_id": "absent"})
        with pytest.raises(NotFoundError):
            project_for_params(session, {"task_ids": ["absent"]})
        with pytest.raises(ValidationError):
            project_for_params(session, {"project_id": other.id, "task_id": tasks[0].id})
        with pytest.raises(ValidationError):
            project_for_params(session, {"task_ids": [tasks[0].id, other_tasks[0].id]})
    assert len(list_projects(db)) == 2
    with pytest.raises(NotFoundError):
        get_task(db, "missing")
    with pytest.raises(NotFoundError):
        get_project(db, "missing")
    with pytest.raises(NotFoundError):
        project_progress(db, project.id, other_tasks[0].package_id)


def test_group_prevents_wrong_owner_and_release_after_submission(db: Database) -> None:
    """A task holder alone may save and release while submission freezes release eligibility."""
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        assign_tasks(
            session, AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="a")
        )
        session.commit()
    assert next_task(db, project.id, "a", tasks[0].package_id) is not None
    with db.session() as session, pytest.raises(AuthorizationError):
        release_task(session, ReleaseTaskParams(request_id="release", task_id=tasks[0].id), "b")
    revision = save(db, tasks[0], "a")
    with db.session() as session:
        submit_task(session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "a")
        session.commit()
    with db.session() as session, pytest.raises(ConflictError):
        release_task(session, ReleaseTaskParams(request_id="release", task_id=tasks[0].id), "a")
    with pytest.raises(ConflictError):
        save(db, tasks[0], "a", previous=revision.id)
    with db.session() as session, pytest.raises(ConflictError):
        submit_task(session, SubmitTaskParams(request_id="again", task_id=tasks[0].id), "a")


def test_review_assignment_prevents_other_reviewer_and_requires_issues(db: Database) -> None:
    """Review assignment owns the review stage; rework always contains an explicit issue list."""
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        assign_tasks(
            session, AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="a")
        )
        session.commit()
    revision = save(db, tasks[0], "a")
    with db.session() as session:
        submit_task(session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "a")
        reviewed = claim_task(
            session,
            ClaimTaskParams(request_id="claim-review", project_id=project.id, stage="review"),
            "q",
        )
        session.commit()
    assert reviewed.state == "in_review"
    with db.session() as session, pytest.raises(AuthorizationError):
        review_task(
            session,
            ReviewTaskParams(
                request_id="review",
                task_id=tasks[0].id,
                revision_id=revision.id,
                decision="approve",
            ),
            "other",
        )
    with db.session() as session, pytest.raises(ValidationError):
        review_task(
            session,
            ReviewTaskParams(
                request_id="review", task_id=tasks[0].id, revision_id=revision.id, decision="rework"
            ),
            "q",
        )
    with db.session() as session, pytest.raises(ConflictError):
        review_task(
            session,
            ReviewTaskParams(
                request_id="review", task_id=tasks[0].id, revision_id="old", decision="approve"
            ),
            "q",
        )
    with db.session() as session:
        release_task(
            session,
            ReleaseTaskParams(request_id="release", task_id=tasks[0].id, stage="review"),
            "q",
        )
        session.commit()
    assert get_task(db, tasks[0].id).state == "submitted"


def test_split_is_once_per_project_and_invalid_packages_are_rejected(db: Database) -> None:
    """Stable partition membership cannot be duplicated by generating a second client request."""
    project, _ = production_fixture(db, "group")
    with db.session() as session, pytest.raises(ConflictError):
        split_packages(session, SplitPackagesParams(request_id="again", project_id=project.id))
    with db.session() as session, pytest.raises(NotFoundError):
        claim_task(
            session,
            ClaimTaskParams(request_id="claim", project_id=project.id, package_id="absent"),
            "a",
        )
    with db.session() as session, pytest.raises(NotFoundError):
        require_task(session, "absent")


def test_revision_rejects_wrong_sample_and_missing_model_provenance(db: Database) -> None:
    """Model import rejects unowned samples and incomplete model version attribution."""
    _, tasks = production_fixture(db)
    for sample, source in (("missing", "human"), (tasks[0].sample_id, "model")):
        with db.session() as session, pytest.raises(ValidationError):
            append_revision(
                session,
                require_task(session, tasks[0].id),
                SaveRevisionParams(
                    request_id=new_id(),
                    task_id=tasks[0].id,
                    previous_revision_id=None,
                    annotation=AnnotationRecord(
                        sample_id=sample, annotator_id="a", labels=("cat",)
                    ),
                    source="model" if source == "model" else "human",
                ),
                "a",
            )


def test_registered_instance_rejects_unknown_or_inactive_assignees(db: Database) -> None:
    """Identity registration closes invalid named assignments while retaining active users."""
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        for actor, status in (
            ("active", "active"),
            ("disabled", "disabled"),
            ("deleted", "deleted"),
        ):
            user = User(
                id=actor,
                display_name=actor,
                status="disabled"
                if status == "disabled"
                else "deleted"
                if status == "deleted"
                else "active",
            )
            session.add(UserRow(id=actor, payload=user.model_dump(mode="json")))
        session.flush()
        session.add(RoleBindingRow(user_id="active", role_id="annotator", project_key=project.id))
        session.commit()
    for actor in ("unknown", "disabled", "deleted"):
        with db.session() as session, pytest.raises(ValidationError, match="registered active"):
            assign_tasks(
                session,
                AssignTasksParams(request_id=new_id(), task_ids=(tasks[0].id,), actor=actor),
            )
    with db.session() as session:
        claimed = claim_task(
            session, ClaimTaskParams(request_id="claim", project_id=project.id), "active"
        )
        session.commit()
    assert claimed.annotator_id == "active"
