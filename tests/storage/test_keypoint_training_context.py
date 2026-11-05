# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Finalized production locks travel once through batches and splits into COCO exports."""

import json
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from datakeel.actions.parameters import ExportParams
from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    FinalizeProjectParams,
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
from datakeel.core.keypoint_models import KeypointDefinition, SkeletonDefinition
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.training_models import SplitRequest
from datakeel.dataset_store.dataset_service import import_paths, list_versions
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.database import Database
from datakeel.storage.production_catalog_changes import manage_template
from datakeel.storage.production_finalize import finalize_project
from datakeel.storage.production_projects import create_project, split_packages
from datakeel.storage.production_queries import list_tasks
from datakeel.storage.production_reviews import submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from datakeel.storage.training_export import training_export_inputs
from datakeel.storage.training_store import create_split
from datakeel.training.export import write_training_export
from tests.storage.production_catalog_fixtures import catalog_project


def _schema() -> SkeletonDefinition:
    return SkeletonDefinition(
        points=(
            KeypointDefinition(id="nose", name="Nose", required=True),
            KeypointDefinition(id="neck", name="Neck"),
        ),
        edges=(("nose", "neck"),),
    )


def _annotation(sample_id: str) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id=sample_id,
        annotator_id="local",
        keypoints=(
            AnnotationSkeleton(
                category="a",
                points=(
                    AnnotationKeypoint(id="neck", x=30, y=40, state="occluded"),
                    AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
                ),
            ),
        ),
        image_width=100,
        image_height=80,
    )


def _project(db: Database, tmp_path: Path, schema: SkeletonDefinition) -> tuple[str, str]:
    catalog_project(db)
    paths = []
    for index in range(2):
        path = tmp_path / f"pose-{index}.png"
        Image.new("RGB", (100, 80)).save(path)
        paths.append(path)
    dataset = import_paths(db, "Poses", paths, {"license": "CC0-1.0"})
    source = list_versions(db, dataset.id)[0]
    with db.session() as session:
        manage_template(
            session,
            CreateLabelSetParams(
                request_id="pose-template",
                target="template",
                template=ProductionTemplate(
                    id="pose",
                    name="Pose",
                    annotation_type="keypoints",
                    keypoint_schema=schema,
                ),
            ),
        )
        project = create_project(
            session,
            CreateProjectParams(
                request_id="pose-project",
                name="Pose",
                dataset_id=dataset.id,
                version_id=source.id,
                label_set_id="labels",
                template_id="pose",
            ),
            "local",
        )
        split_packages(session, SplitPackagesParams(request_id="packages", project_id=project.id))
        session.commit()
    return dataset.id, project.id


def _submit_all(db: Database, project_id: str) -> None:
    for task in list_tasks(db, project_id):
        with db.session() as session:
            append_revision(
                session,
                require_task(session, task.id),
                SaveRevisionParams(
                    request_id=f"save-{task.id}",
                    task_id=task.id,
                    previous_revision_id=None,
                    annotation=_annotation(task.sample_id),
                ),
                "local",
            )
            submit_task(
                session, SubmitTaskParams(request_id=f"submit-{task.id}", task_id=task.id), "local"
            )
            session.commit()


def _finalize(db: Database, project_id: str, schema: SkeletonDefinition) -> str:
    with db.session() as session:
        result = finalize_project(
            session, FinalizeProjectParams(request_id="final", project_id=project_id)
        )
        version_id = str(result.details["version_id"])
        batch = session.scalar(
            select(AnnotationBatchRow).where(AnnotationBatchRow.version_id == version_id)
        )
        assert batch is not None
        assert batch.batch["keypoint_schema"] == schema.model_dump(mode="json")
        session.commit()
    return version_id


def test_finalized_split_and_coco_share_one_locked_schema(db: Database, tmp_path: Path) -> None:
    """The export uses the finalized template rather than record order or copied schemas."""
    schema = _schema()
    dataset_id, project_id = _project(db, tmp_path, schema)
    _submit_all(db, project_id)
    version_id = _finalize(db, project_id, schema)
    split = create_split(db, dataset_id, version_id, SplitRequest(name="poses"))
    assert split.keypoint_schema == schema
    with db.session() as session:
        export = training_export_inputs(
            session,
            ExportParams(
                dataset_id=dataset_id,
                version_id=version_id,
                split_set_id=split.id,
                format="coco",
            ),
            materialize=True,
        )
        assert export.keypoint_schema == schema
    write_training_export(export, tmp_path / "package", tmp_path / "poses.tar")
    raw = json.loads((tmp_path / "package/annotations/instances_train.json").read_text())
    assert raw["categories"][0]["keypoints"] == ["Nose", "Neck"]
    assert raw["categories"][0]["skeleton"] == [[1, 2]]
    assert raw["annotations"][0]["keypoints"] == [10, 20, 2, 30, 40, 1]
