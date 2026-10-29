# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline model execution, import partial success and approved project finalization."""

import json
from typing import Literal

import pytest
from sqlalchemy import select

from datakeel.actions.production_catalog_parameters import (
    FinalizeProjectParams,
    ImportPredictionsParams,
    RunPrelabelParams,
)
from datakeel.actions.production_parameters import SubmitTaskParams
from datakeel.core.errors import ConflictError
from datakeel.core.production_catalog_models import PredictionFile
from datakeel.core.production_models import AnnotationRevision
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.annotation_store import get_annotation_quality
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.production_catalog_plans import (
    catalog_manifest,
    catalog_requires_approval,
    catalog_state,
)
from datakeel.storage.production_finalize import finalize_project
from datakeel.storage.production_predictions import import_predictions, run_prelabel
from datakeel.storage.production_reviews import submit_task
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionReviewRow,
    ProductionRevisionRow,
)
from datakeel.storage.production_tasks import require_project, require_task
from datakeel.storage.version_diff import version_summary
from tests.storage.production_catalog_fixtures import catalog_project


def test_prediction_import_keeps_valid_files_and_precise_model_provenance(db: Database) -> None:
    """A bad YOLO file does not roll back a valid file or lose its model version/confidence."""
    fixture = catalog_project(db)
    params = ImportPredictionsParams(
        request_id="import",
        project_id=fixture.project.id,
        model_id="fake",
        format="yolo",
        files=(
            PredictionFile(filename="sample-0.txt", content="0 0.5 0.5 0.5 0.5 0.7"),
            PredictionFile(filename="sample-1.txt", content="99 0.5 0.5 0.5 0.5"),
            PredictionFile(filename="broken.txt", content="bad"),
        ),
    )
    with db.session() as session:
        result = import_predictions(session, params, "local")
        session.commit()
        assert len(result.revision_ids) == 1
        assert len(result.failures) == 2
        row = session.get(ProductionRevisionRow, result.revision_ids[0])
        assert row is not None
        revision = AnnotationRevision.model_validate(row.payload)
        assert (
            revision.source,
            revision.model_name,
            revision.model_version,
            revision.confidence,
        ) == (
            "model",
            "Generated model",
            "1",
            0.7,
        )
        assert revision.previous_revision_id is None
        assert not list(session.scalars(select(ProductionAssignmentRow)))
        assert not list(session.scalars(select(ProductionReviewRow)))


@pytest.mark.parametrize("prediction_format", ["yolo", "coco"])
def test_prediction_import_persists_clipped_edge_boxes(
    db: Database, prediction_format: Literal["yolo", "coco"]
) -> None:
    """Rounded edge boxes survive import and the strict saved-revision geometry validation."""
    fixture = catalog_project(db)
    content = (
        "0 0.81 0.5 0.38 0.2"
        if prediction_format == "yolo"
        else json.dumps(
            [{"image_id": "sample-0", "category_id": "a", "bbox": [62, 32, 38.000000000000014, 16]}]
        )
    )
    params = ImportPredictionsParams(
        request_id="edge-import",
        project_id=fixture.project.id,
        model_id="fake",
        format=prediction_format,
        category_mapping={"a": "a"},
        files=(PredictionFile(filename="sample-0.txt", content=content),),
    )
    with db.session() as session:
        result = import_predictions(session, params, "local")
        session.commit()
    assert not result.failures
    assert len(result.revision_ids) == 1
    with db.session() as session:
        row = session.get(ProductionRevisionRow, result.revision_ids[0])
        assert row is not None
        revision = AnnotationRevision.model_validate(row.payload)
        assert revision.annotation.boxes is not None
        box = revision.annotation.boxes[0]
        assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx((62, 32, 100, 48))
        assert box.x2 == 100
        assert require_task(session, fixture.tasks[0].id).latest_revision_id == revision.id


def test_fake_prelabel_budget_and_finalization_reuse_annotation_batches(db: Database) -> None:
    """Only approved task heads finalize into a new compatible version in one transaction."""
    fixture = catalog_project(db)
    params = RunPrelabelParams(
        request_id="fake", project_id=fixture.project.id, model_id="fake", budget=0.1
    )
    with db.session() as session:
        assert catalog_requires_approval(session, params)
        assert not catalog_requires_approval(session, params.model_copy(update={"budget": 0.5}))
        state = catalog_state(session, params)
        assert catalog_manifest(session, params).state_digest == state
        run = run_prelabel(session, params, "local")
        assert len(run.revision_ids) == 2
        assert run.cost == 0.5
        assert run.confidences == (0.95, 0.95)
        assert catalog_state(session, params) != state
        finalize = FinalizeProjectParams(request_id="finalize", project_id=fixture.project.id)
        with pytest.raises(ConflictError, match="approved"):
            finalize_project(session, finalize)
        for task in fixture.tasks:
            submit_task(session, SubmitTaskParams(request_id=task.id, task_id=task.id), "local")
        output = finalize_project(session, finalize)
        version_id = str(output.details["version_id"])
        session.commit()
        version = session.get(VersionRow, version_id)
        assert version is not None
        assert version.dataset_id == fixture.project.dataset_id
        summary = version_summary(
            session, require_dataset(session, fixture.project.dataset_id), version_id
        )
        assert summary.annotation_count == 2
        assert summary.label_count == 2
        assert require_project(session, fixture.project.id).finalized_version_id == version_id
        assert all(require_task(session, task.id).state == "finalized" for task in fixture.tasks)
        assert output.details["produced_by_project"] == fixture.project.id
        assert len(list(session.scalars(select(AnnotationBatchRow)))) == 1
        assert not list(session.scalars(select(ProductionReviewRow)))
        assert not list(session.scalars(select(ProductionAssignmentRow)))
    report = get_annotation_quality(db, fixture.project.dataset_id, version_id)
    assert report.latest is not None
    assert report.latest.sample_count == 2
    assert report.latest.annotation_count == 2


def test_prediction_state_errors_are_isolated_per_image(db: Database) -> None:
    """An already submitted task reports a file failure while another task still imports."""
    fixture = catalog_project(db)
    run_params = RunPrelabelParams(
        request_id="fake", project_id=fixture.project.id, model_id="fake", budget=1
    )
    with db.session() as session:
        run_prelabel(session, run_params, "local")
        submit_task(
            session, SubmitTaskParams(request_id="submit", task_id=fixture.tasks[0].id), "local"
        )
        document = {
            "images": [
                {"id": index, "file_name": f"sample-{index}.png", "width": 100, "height": 80}
                for index in range(2)
            ],
            "categories": [{"id": 1, "name": "a"}],
            "annotations": [
                {"image_id": index, "category_id": 1, "bbox": [0, 0, 10, 10]} for index in range(2)
            ],
        }
        result = import_predictions(
            session,
            ImportPredictionsParams(
                request_id="import",
                project_id=fixture.project.id,
                model_id="fake",
                format="coco",
                files=(PredictionFile(filename="predictions.json", content=json.dumps(document)),),
            ),
            "local",
        )
        assert len(result.revision_ids) == 1
        assert len(result.failures) == 1
        assert result.failures[0].code == "revision_rejected"
