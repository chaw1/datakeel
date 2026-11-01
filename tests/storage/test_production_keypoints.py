# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production saves and locked-template upgrades enforce native skeleton semantics."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    FinalizeProjectParams,
    UpgradeProjectTemplateParams,
)
from datakeel.actions.production_parameters import (
    CreateProjectParams,
    SaveRevisionParams,
    SplitPackagesParams,
    SubmitTaskParams,
)
from datakeel.core.annotation_models import (
    AnnotationKeypoint,
    AnnotationRecord,
    AnnotationSkeleton,
)
from datakeel.core.errors import ValidationError
from datakeel.core.keypoint_models import KeypointDefinition, SkeletonDefinition
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.production_models import AnnotationRevision, ProductionTask, Project
from datakeel.storage.database import Database
from datakeel.storage.production_catalog_changes import manage_template
from datakeel.storage.production_catalog_rows import ProductionTemplateRow
from datakeel.storage.production_finalize import finalize_project
from datakeel.storage.production_projects import create_project, split_packages
from datakeel.storage.production_reviews import submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import require_task, task_view
from datakeel.storage.production_template_upgrade import upgrade_plan, upgrade_project_template
from tests.storage.production_catalog_fixtures import catalog_project


def _schema(*, wrist_required: bool = False) -> SkeletonDefinition:
    return SkeletonDefinition(
        points=(
            KeypointDefinition(id="nose", name="Nose", required=True),
            KeypointDefinition(id="neck", name="Neck"),
            KeypointDefinition(id="wrist", name="Wrist", required=wrist_required),
        ),
        edges=(("nose", "neck"), ("neck", "wrist")),
    )


def _template(revision: int = 1, *, wrist_required: bool = False) -> ProductionTemplate:
    return ProductionTemplate(
        id="pose",
        name="Pose",
        annotation_type="keypoints",
        component_config={"components": ["keypoints", "box"]},
        keypoint_schema=_schema(wrist_required=wrist_required),
        revision=revision,
    )


def _project(db: Database) -> tuple[Project, tuple[ProductionTask, ...]]:
    catalog_project(db)
    with db.session() as session:
        manage_template(
            session,
            CreateLabelSetParams(request_id="pose", target="template", template=_template()),
        )
        project = create_project(
            session,
            CreateProjectParams(
                request_id="pose-project",
                name="Pose",
                dataset_id="catalog-data",
                version_id="catalog-source",
                label_set_id="labels",
                template_id="pose",
            ),
            "local",
        )
        split_packages(session, SplitPackagesParams(request_id="pose-split", project_id=project.id))
        tasks = tuple(
            task_view(row)
            for row in session.scalars(
                select(ProductionTaskRow)
                .where(ProductionTaskRow.project_id == project.id)
                .order_by(ProductionTaskRow.id)
            )
        )
        session.commit()
    return project, tasks


def _annotation(task: ProductionTask, *, complete: bool = True) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="local",
        keypoints=(
            AnnotationSkeleton(
                category="a",
                points=(
                    AnnotationKeypoint(id="wrist", x=30, y=40, state="occluded")
                    if complete
                    else AnnotationKeypoint(id="wrist", state="missing"),
                    AnnotationKeypoint(id="nose", x=10, y=20, state="visible")
                    if complete
                    else AnnotationKeypoint(id="nose", state="missing"),
                ),
                attributes={"side": "left"},
            ),
        ),
        boxes=(),
        image_width=100,
        image_height=80,
    )


def _save(
    session: Session, task: ProductionTask, annotation: AnnotationRecord
) -> AnnotationRevision:
    row = require_task(session, task.id)
    return append_revision(
        session,
        row,
        SaveRevisionParams(
            request_id=f"save-{task.id}",
            task_id=task.id,
            previous_revision_id=task.latest_revision_id,
            annotation=annotation,
        ),
        "local",
    )


def test_save_aligns_ids_and_draft_all_missing_cannot_submit(db: Database) -> None:
    """The server normalizes a draft by ID and rejects its incomplete submission."""
    _, tasks = _project(db)
    with db.session() as session:
        revision = _save(session, tasks[0], _annotation(tasks[0], complete=False))
        [skeleton] = list(revision.annotation.keypoints or ())
        assert [point.id for point in skeleton.points] == ["nose", "neck", "wrist"]
        assert all(point.state == "missing" for point in skeleton.points[:2])
        with pytest.raises(ValidationError, match="at least one"):
            submit_task(
                session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "local"
            )


def test_valid_skeleton_submits_and_finalization_rechecks_new_required_points(db: Database) -> None:
    """A template upgrade can affect approved work, but finalization still rejects it."""
    project, tasks = _project(db)
    with db.session() as session:
        for task in tasks:
            _save(session, task, _annotation(task))
            submit_task(
                session, SubmitTaskParams(request_id=f"submit-{task.id}", task_id=task.id), "local"
            )
        manage_template(
            session,
            CreateLabelSetParams(
                request_id="require-wrist",
                target="template",
                operation="update",
                template=_template().model_copy(
                    update={
                        "keypoint_schema": _schema().model_copy(
                            update={
                                "points": (
                                    *_schema().points,
                                    KeypointDefinition(id="new", name="New", required=True),
                                )
                            }
                        )
                    }
                ),
            ),
        )
        plan = upgrade_plan(
            session, UpgradeProjectTemplateParams(request_id="preview", project_id=project.id)
        )
        assert plan.invalid_task_count == len(tasks)
        assert all("new" in problem for item in plan.invalid_tasks for problem in item.problems)
        upgrade_project_template(
            session, UpgradeProjectTemplateParams(request_id="upgrade", project_id=project.id)
        )
        with pytest.raises(ValidationError, match="new"):
            finalize_project(
                session, FinalizeProjectParams(request_id="final", project_id=project.id)
            )


def test_template_reorder_and_optional_addition_keep_old_points_aligned(db: Database) -> None:
    """Order, edge and optional-point changes do not invalidate historical IDs."""
    project, tasks = _project(db)
    with db.session() as session:
        _save(session, tasks[0], _annotation(tasks[0]))
        reordered = _schema().model_copy(
            update={
                "points": (
                    KeypointDefinition(id="neck", name="Neck"),
                    KeypointDefinition(id="new", name="New optional"),
                    KeypointDefinition(id="nose", name="Nose", required=True),
                    KeypointDefinition(id="wrist", name="Wrist"),
                )
            }
        )
        manage_template(
            session,
            CreateLabelSetParams(
                request_id="reorder",
                target="template",
                operation="update",
                template=_template().model_copy(update={"keypoint_schema": reordered}),
            ),
        )
        plan = upgrade_plan(
            session, UpgradeProjectTemplateParams(request_id="preview", project_id=project.id)
        )
        assert plan.invalid_task_count == 0
        assert plan.annotation_object_count == 1


def test_used_point_cannot_be_deleted_or_renamed(db: Database) -> None:
    """Historical point use prevents destructive template edits."""
    _, tasks = _project(db)
    with db.session() as session:
        _save(session, tasks[0], _annotation(tasks[0]))
        changed = _schema().model_copy(update={"points": _schema().points[:2]})
        with pytest.raises(ValidationError, match="wrist"):
            manage_template(
                session,
                CreateLabelSetParams(
                    request_id="delete-used",
                    target="template",
                    operation="update",
                    template=_template().model_copy(update={"keypoint_schema": changed}),
                ),
            )


def test_new_keypoint_template_and_project_require_schema(db: Database) -> None:
    """Legacy rows remain readable but cannot create new templates or projects."""
    catalog_project(db)
    legacy = ProductionTemplate(id="legacy", name="Legacy", annotation_type="keypoints")
    with db.session() as session:
        with pytest.raises(ValidationError, match="keypoint_schema"):
            manage_template(
                session,
                CreateLabelSetParams(request_id="legacy", target="template", template=legacy),
            )
        session.rollback()
        session.add(
            ProductionTemplateRow(id=legacy.id, revision=1, payload=legacy.model_dump(mode="json"))
        )
        session.flush()
        with pytest.raises(ValidationError, match="keypoint_schema"):
            create_project(
                session,
                CreateProjectParams(
                    request_id="legacy-project",
                    name="Legacy",
                    dataset_id="catalog-data",
                    version_id="catalog-source",
                    label_set_id="labels",
                    template_id="legacy",
                ),
                "local",
            )
