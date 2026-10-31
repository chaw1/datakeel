# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Projects keep the template version they locked until a signed upgrade moves only them."""

from pathlib import Path

import pytest
from sqlalchemy import select

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.storage.database import Database
from datakeel.storage.production_catalog import require_template
from datakeel.storage.production_catalog_rows import ProductionTemplateVersionRow
from datakeel.storage.production_queries import get_project
from datakeel.storage.workbench_reads import workbench_project
from tests.production_team_ops import failure
from tests.storage.template_lock_support import (
    LABELS,
    TEMPLATE,
    box,
    change_template,
    plan_details,
    prepare_upgrade,
    save,
    seed_two_projects,
)
from tests.workbench_helpers import run_action

LOCAL = AccessContext(actor="local", entry="ask", scope="query")


def _sign(db: Database, plan_id: str, digest: str) -> None:
    approve_plan(db, plan_id, ApprovalDecision(approve=True, plan_digest=digest))
    run = execute_plan(db, plan_id, ExecuteRequest(plan_digest=digest))
    assert run.status == "SUCCEEDED", run.error


def test_template_and_label_changes_leave_both_sharing_projects_unchanged(
    db: Database, tmp_path: Path
) -> None:
    """A new required attribute and a deleted label change neither project's form or checks."""
    (first, first_tasks), (second, second_tasks) = seed_two_projects(db, tmp_path / "src")
    assert first.template_version == second.template_version == 1
    change_template(db)
    for project, tasks in ((first, first_tasks), (second, second_tasks)):
        assert failure(lambda tasks=tasks: save(db, tasks[0], [box("dog"), box("cat", 30)])) is None
        view = workbench_project(db, project.id, LOCAL)
        assert view.template is not None
        assert view.template.revision == 1
        assert view.template.attributes == ()
        assert view.label_set.version == 1
        assert view.latest_template is not None
        assert view.latest_template.revision == 2
        assert view.latest_label_set_version == 2
        assert get_project(db, project.id).template_version == 1


def test_upgrade_plan_counts_changes_and_non_compliant_annotations_exactly(
    db: Database, tmp_path: Path
) -> None:
    """The plan names both version moves, every diff and each failing current revision."""
    (first, tasks), _ = seed_two_projects(db, tmp_path / "src", count=4)
    save(db, tasks[0], [box("dog"), box("cat", 30)])
    save(db, tasks[1], [box("cat")])
    save(db, tasks[2], [])
    change_template(db)
    plan = prepare_upgrade(db, first.id)
    assert plan.requires_approval
    assert plan.impact.object_count == 4
    details = plan_details(plan)
    assert (details.from_template_version, details.to_template_version) == (1, 2)
    assert (details.from_label_set_version, details.to_label_set_version) == (1, 2)
    assert details.labels.added == ("bird",)
    assert details.labels.removed == ("dog",)
    assert details.attributes.added == details.attributes.required == ("object:colour",)
    assert details.settings_changed == ()
    assert (details.task_count, details.annotated_task_count) == (4, 3)
    assert details.annotation_object_count == 3
    assert (details.invalid_task_count, details.invalid_object_count) == (2, 3)
    failing = {item.task_id: item for item in details.invalid_tasks}
    assert set(failing) == {tasks[0].id, tasks[1].id}
    assert failing[tasks[0].id].invalid_objects == 2
    assert failing[tasks[0].id].problems == (
        'box 1 label "dog" is not in label set v2',
        'Attribute "colour" is required on box 1',
        'Attribute "colour" is required on box 2',
    )
    assert failing[tasks[1].id].invalid_objects == 1


def test_signed_upgrade_changes_only_that_project_and_its_checks(
    db: Database, tmp_path: Path
) -> None:
    """Nothing moves before signing; after it only the upgraded project enforces v2."""
    (first, first_tasks), (second, second_tasks) = seed_two_projects(db, tmp_path / "src")
    change_template(db)
    plan = prepare_upgrade(db, first.id)
    assert get_project(db, first.id).template_version == 1
    _sign(db, plan.id, plan.plan_digest)
    upgraded = get_project(db, first.id)
    assert (upgraded.template_version, upgraded.label_set_version) == (2, 2)
    untouched = get_project(db, second.id)
    assert (untouched.template_version, untouched.label_set_version) == (1, 1)
    with pytest.raises(ValidationError, match="colour"):
        save(db, first_tasks[0], [box("cat")])
    with pytest.raises(ValidationError, match="label set"):
        save(db, first_tasks[1], [box("dog", colour="red")])
    save(db, first_tasks[2], [box("cat", colour="red")])
    save(db, second_tasks[0], [box("dog")])
    view = workbench_project(db, first.id, LOCAL)
    assert view.template is not None
    assert [item.key for item in view.template.attributes] == ["colour"]


def test_unsigned_upgrade_cannot_execute_and_a_new_save_voids_the_plan(
    db: Database, tmp_path: Path
) -> None:
    """Agents only prepare; a revision saved after preparing changes the frozen counts."""
    (first, tasks), _ = seed_two_projects(db, tmp_path / "src")
    change_template(db)
    plan = prepare_upgrade(db, first.id)
    with pytest.raises(AuthorizationError, match="approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert get_project(db, first.id).template_version == 1
    stale = prepare_upgrade(db, first.id)
    save(db, tasks[0], [box("cat")])
    with pytest.raises(ConflictError, match="state changed"):
        approve_plan(db, stale.id, ApprovalDecision(approve=True, plan_digest=stale.plan_digest))
    assert get_project(db, first.id).template_version == 1


def test_upgrade_refuses_no_change_downgrade_and_archived_targets(
    db: Database, tmp_path: Path
) -> None:
    """Explicit targets must be newer, saved and not archived; a current project has no plan."""
    (first, _), _ = seed_two_projects(db, tmp_path / "src")
    with pytest.raises(ValidationError, match="already uses"):
        prepare_upgrade(db, first.id)
    change_template(db)
    plan = prepare_upgrade(db, first.id, template_version=2, label_set_version=1)
    details = plan_details(plan)
    assert (details.to_template_version, details.to_label_set_version) == (2, 1)
    _sign(db, plan.id, plan.plan_digest)
    downgrade = failure(lambda: prepare_upgrade(db, first.id, template_version=1))
    assert isinstance(downgrade, ValidationError)
    assert "Template downgrades" in str(downgrade)
    labels = prepare_upgrade(db, first.id)
    assert plan_details(labels).attributes.added == ()
    _sign(db, labels.id, labels.plan_digest)
    with pytest.raises(ValidationError, match="Label-set downgrades"):
        prepare_upgrade(db, first.id, label_set_version=1, template_version=2)
    with db.session() as session:
        current = require_template(session, TEMPLATE)
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "delete",
            "template": current.model_dump(mode="json"),
        },
    )
    with pytest.raises(ValidationError, match="archived"):
        prepare_upgrade(db, first.id, template_version=3)
    assert get_project(db, first.id).label_set_id == LABELS


def test_archived_template_keeps_serving_projects_locked_before_archival(
    db: Database, tmp_path: Path
) -> None:
    """Archiving creates a version for future projects; locked projects keep annotating."""
    (first, tasks), _ = seed_two_projects(db, tmp_path / "src")
    with db.session() as session:
        current = require_template(session, TEMPLATE)
    run_action(
        db,
        "create_label_set",
        {"target": "template", "operation": "delete", "template": current.model_dump(mode="json")},
    )
    save(db, tasks[0], [box("cat")])
    view = workbench_project(db, first.id, LOCAL)
    assert view.template is not None
    assert not view.template.archived
    assert view.latest_template is not None
    assert view.latest_template.archived


def test_every_saved_revision_stays_readable_for_an_explicit_upgrade(
    db: Database, tmp_path: Path
) -> None:
    """An upgrade can target an intermediate version after newer edits replaced it."""
    (first, _), _ = seed_two_projects(db, tmp_path / "src")
    change_template(db)
    with db.session() as session:
        current = require_template(session, TEMPLATE)
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "update",
            "template": {**current.model_dump(mode="json"), "name": "Lock v3"},
        },
    )
    with db.engine.connect() as connection:
        saved = connection.scalars(
            select(ProductionTemplateVersionRow.revision)
            .where(ProductionTemplateVersionRow.template_id == TEMPLATE)
            .order_by(ProductionTemplateVersionRow.revision)
        ).all()
    assert saved == [1, 2, 3]
    plan = prepare_upgrade(db, first.id, template_version=2, label_set_version=1)
    assert plan_details(plan).settings_changed == ()
    _sign(db, plan.id, plan.plan_digest)
    view = workbench_project(db, first.id, LOCAL)
    assert view.template is not None
    assert (view.template.revision, view.template.name) == (2, "Lock")
    assert view.latest_template is not None
    assert view.latest_template.name == "Lock v3"
