# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tier upgrades preserve unfinished personal ownership without reopening approved work."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.production_parameters import (
    ClaimTaskParams,
    ReleaseTaskParams,
    SaveRevisionParams,
    SubmitTaskParams,
    UpgradeProjectParams,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.identity_models import User
from datakeel.core.models import new_id, utcnow
from datakeel.storage.identity_rows import UserRow
from datakeel.storage.production_assignments import claim_task, create_assignment, release_task
from datakeel.storage.production_projects import upgrade_project
from datakeel.storage.production_queries import (
    get_task,
    list_assignments,
    list_revisions,
    project_progress,
)
from datakeel.storage.production_reviews import submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task, transition_task
from tests.production_helpers import production_fixture
from tests.storage.test_production_workflow import save

if TYPE_CHECKING:
    from datakeel.core.production_models import WorkflowTier
    from datakeel.storage.database import Database


def _upgrade(db: Database, project_id: str, tier: WorkflowTier) -> None:
    with db.session() as session:
        upgrade_project(
            session,
            UpgradeProjectParams(request_id=new_id(), project_id=project_id, workflow_tier=tier),
        )
        session.commit()


@pytest.mark.parametrize("state", ["pending", "in_progress"])
def test_upgrade_restores_author_assignment_and_release_requires_reclaim(
    db: Database, state: str
) -> None:
    """Restored ownership works in both editable states and never bypasses later release."""
    project, tasks = production_fixture(db, count=1)
    first = save(db, tasks[0], "author")
    if state == "pending":
        with db.session() as session:
            transition_task(session, require_task(session, tasks[0].id), "pending")
            session.commit()
    before = get_task(db, tasks[0].id)
    progress = project_progress(db, project.id)
    _upgrade(db, project.id, "group")
    assert get_task(db, before.id) == before
    assert project_progress(db, project.id) == progress
    assignments = list_assignments(db, before.id)
    assert len(assignments) == 1
    assert (assignments[0].actor, assignments[0].stage, assignments[0].active) == (
        "author",
        "annotation",
        True,
    )
    _upgrade(db, project.id, "team")
    assert list_assignments(db, before.id) == assignments
    save(db, before, "author", previous=first.id)
    with db.session() as session:
        released = release_task(
            session, ReleaseTaskParams(request_id=new_id(), task_id=before.id), "author"
        )
        session.commit()
    with pytest.raises(AuthorizationError):
        save(db, released, "author", previous=released.latest_revision_id)
    with db.session() as session:
        claimed = claim_task(
            session, ClaimTaskParams(request_id=new_id(), project_id=project.id), "author"
        )
        session.commit()
    assert (claimed.id, claimed.round) == (before.id, 0)
    assert list_revisions(db, before.id)[0] == first


@pytest.mark.parametrize("tier", ["group", "team"])
def test_upgrade_skips_unowned_model_only_and_approved_personal_tasks(
    db: Database, tier: WorkflowTier
) -> None:
    """Queue tasks and model provenance never become human owners; approvals remain sealed."""
    project, tasks = production_fixture(db, count=3)
    approved = save(db, tasks[0], "author")
    with db.session() as session:
        submit_task(session, SubmitTaskParams(request_id=new_id(), task_id=tasks[0].id), "author")
        model = append_revision(
            session,
            require_task(session, tasks[1].id),
            SaveRevisionParams(
                request_id=new_id(),
                task_id=tasks[1].id,
                previous_revision_id=None,
                annotation=AnnotationRecord(
                    sample_id=tasks[1].sample_id, annotator_id="model:fixture", labels=("cat",)
                ),
                source="model",
                model_name="fixture",
                model_version="1",
            ),
            "prediction-importer",
        )
        session.commit()
    before = tuple(get_task(db, task.id) for task in tasks)
    _upgrade(db, project.id, tier)
    assert tuple(get_task(db, task.id) for task in tasks) == before
    assert all(list_assignments(db, task.id) == () for task in tasks)
    assert list_revisions(db, tasks[0].id) == (approved,)
    assert list_revisions(db, tasks[1].id) == (model,)
    with pytest.raises(AuthorizationError):
        save(db, before[0], "author", previous=approved.id)


@pytest.mark.parametrize("author_status", ["unregistered", "disabled"])
def test_upgrade_preserves_historical_author_without_granting_new_assignment_authority(
    db: Database, author_status: str
) -> None:
    """An archived or pre-registration author cannot block migration or gain fresh work."""
    project, tasks = production_fixture(db, count=2)
    revision = save(db, tasks[0], "historical-author")
    with db.session() as session:
        session.add(
            UserRow(
                id="administrator",
                payload=User(
                    id="administrator", display_name="Administrator", created_at=utcnow()
                ).model_dump(mode="json"),
            )
        )
        if author_status == "disabled":
            session.add(
                UserRow(
                    id="historical-author",
                    payload=User(
                        id="historical-author",
                        display_name="Former author",
                        status="disabled",
                        created_at=utcnow(),
                    ).model_dump(mode="json"),
                )
            )
        session.commit()
    before = get_task(db, tasks[0].id)
    _upgrade(db, project.id, "group")
    assert get_task(db, before.id) == before
    assert list_revisions(db, before.id) == (revision,)
    assignments = list_assignments(db, before.id)
    assert len(assignments) == 1
    assert (assignments[0].actor, assignments[0].active) == ("historical-author", True)
    with db.session() as session, pytest.raises(ValidationError, match="registered active"):
        create_assignment(
            session, require_task(session, tasks[1].id), "historical-author", "annotation"
        )
