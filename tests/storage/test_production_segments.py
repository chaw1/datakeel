# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Segment production saves, locked-source revalidation, upgrades and finalization."""

from collections.abc import Callable

import pytest
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    FinalizeProjectParams,
    UpgradeProjectTemplateParams,
)
from datakeel.actions.production_parameters import (
    AssignTasksParams,
    CreateProjectParams,
    ReviewTaskParams,
    SaveRevisionParams,
    SplitPackagesParams,
    SubmitTaskParams,
)
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSegment,
)
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.errors import ValidationError
from datakeel.core.production_attributes import TemplateAttribute
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.production_models import ProductionTask, Project, WorkflowTier
from datakeel.dataset_store.rows import VersionRow
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.annotation_store import import_annotations_in_session
from datakeel.storage.database import Database
from datakeel.storage.production_assignments import assign_tasks
from datakeel.storage.production_catalog import validate_template_content
from datakeel.storage.production_catalog_changes import manage_template
from datakeel.storage.production_finalize import finalize_project
from datakeel.storage.production_projects import create_project, split_packages
from datakeel.storage.production_reviews import review_task, submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import require_task, task_view
from datakeel.storage.production_template_upgrade import upgrade_plan
from tests.storage.production_catalog_fixtures import catalog_project


def _reject(call: Callable[[], object], match: str) -> None:
    message = None
    try:
        call()
    except ValidationError as error:
        message = str(error)
    assert message is not None, "Expected segment workflow validation to reject the operation"
    assert match in message


def segment_source(db: Database, *, probe: bool = True, duration: int = 3250) -> None:
    """Create two locked audio sources with optional real-looking probe metadata."""
    catalog_project(db)
    with db.session() as session:
        version = session.get(VersionRow, "catalog-source")
        assert version is not None
        manifest: list[dict[str, JsonValue]] = []
        for raw in version.manifest:
            metadata = dict(raw.get("metadata", {}))
            if probe:
                metadata["media_probe"] = {
                    "duration_ms": duration,
                    "codec": "pcm_s16le",
                    "format": "wav",
                }
            manifest.append(
                {
                    **raw,
                    "path": f"{raw['id']}.wav",
                    "filename": f"{raw['id']}.wav",
                    "modality": "audio",
                    "metadata": metadata,
                }
            )
        version.manifest = manifest
        session.commit()


def _template(
    kind: str = "segment", revision: int = 1, rules: dict[str, JsonValue] | None = None
) -> ProductionTemplate:
    return ProductionTemplate(
        id=kind,
        name=kind,
        annotation_type="segment" if kind == "segment" else "box",
        component_config={"components": [kind, "classification"]},
        validation_rules=rules or {"min_annotations": 1, "max_annotations": 5},
        attributes=(
            TemplateAttribute(
                key="note", name_zh="说明", name_en="Note", type="text", required=True
            ),
        )
        if kind == "segment"
        else (),
        revision=revision,
    )


def segment_project(
    db: Database,
    tier: WorkflowTier = "personal",
    *,
    kind: str = "segment",
    rules: dict[str, JsonValue] | None = None,
) -> tuple[Project, tuple[ProductionTask, ...]]:
    """Create a segment project and its two generated tasks."""
    with db.session() as session:
        manage_template(
            session,
            CreateLabelSetParams(
                request_id=f"template-{kind}",
                target="template",
                template=_template(kind, rules=rules),
            ),
        )
        project = create_project(
            session,
            CreateProjectParams(
                request_id=f"project-{kind}",
                name=kind,
                dataset_id="catalog-data",
                version_id="catalog-source",
                label_set_id="labels",
                template_id=kind,
                workflow_tier=tier,
            ),
            "local",
        )
        split_packages(
            session, SplitPackagesParams(request_id=f"split-{kind}", project_id=project.id)
        )
        rows = tuple(
            session.scalars(
                select(ProductionTaskRow)
                .where(ProductionTaskRow.project_id == project.id)
                .order_by(ProductionTaskRow.id)
            )
        )
        if tier != "personal":
            for row in rows:
                assign_tasks(
                    session,
                    AssignTasksParams(
                        request_id=f"assign-{row.id}", task_ids=(row.id,), actor="local"
                    ),
                )
        session.commit()
        return project, tuple(task_view(row) for row in rows)


def segment_annotation(task: ProductionTask, *, duration: int = 3250) -> AnnotationRecord:
    """Build two overlapping, fully attributed segments on one task."""
    return AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="local",
        labels=(),
        segments=(
            AnnotationSegment(category="a", start_ms=0, end_ms=1000, attributes={"note": "开始"}),
            AnnotationSegment(
                category="a", start_ms=500, end_ms=duration, attributes={"note": "重叠"}
            ),
        ),
        media_duration_ms=duration,
    )


def _save(session: Session, task: ProductionTask, annotation: AnnotationRecord) -> None:
    append_revision(
        session,
        require_task(session, task.id),
        SaveRevisionParams(
            request_id=f"save-{task.id}",
            task_id=task.id,
            previous_revision_id=task.latest_revision_id,
            annotation=annotation,
        ),
        "local",
    )


def test_segment_personal_save_submit_and_finalize_roundtrip(db: Database) -> None:
    """Personal finalization retains exact segments through the native annotation importer."""
    segment_source(db)
    project, tasks = segment_project(db)
    with db.session() as session:
        for task in tasks:
            _save(session, task, segment_annotation(task))
            submit_task(
                session, SubmitTaskParams(request_id=f"submit-{task.id}", task_id=task.id), "local"
            )
        result = finalize_project(
            session, FinalizeProjectParams(request_id="finalize", project_id=project.id)
        )
        version_id = str(result.details["version_id"])
        batch = session.scalar(
            select(AnnotationBatchRow).where(AnnotationBatchRow.version_id == version_id)
        )
        assert batch is not None
        stored = AnnotationBatch.model_validate(batch.batch)
        assert stored.annotations[0].segments is not None
        assert stored.annotations[0].segments[0].start_ms == 0


def test_every_save_revalidates_probe_duration_and_required_segment_attributes(
    db: Database,
) -> None:
    """Every human save checks source duration and required per-segment fields."""
    segment_source(db)
    _, tasks = segment_project(db)
    with db.session() as session:
        with pytest.raises(ValidationError, match="media_duration_ms"):
            _save(session, tasks[0], segment_annotation(tasks[0], duration=3249))
        broken = segment_annotation(tasks[0]).model_copy(
            update={
                "segments": (AnnotationSegment(category="a", start_ms=0, end_ms=1, attributes={}),)
            }
        )
        with pytest.raises(ValidationError, match="required"):
            _save(session, tasks[0], broken)


def test_project_creation_checks_every_source_even_without_revisions(db: Database) -> None:
    """A segment project cannot be created until every source has a positive probe."""
    segment_source(db, probe=False)
    _reject(lambda: segment_project(db), "run the media probe")


def test_template_upgrade_checks_unprobed_sources_before_impact_plan(db: Database) -> None:
    """Upgrading to segments checks sources independently of existing revision history."""
    segment_source(db, probe=False)
    project, _ = segment_project(db, kind="box")
    with db.session() as session:
        manage_template(
            session,
            CreateLabelSetParams(
                request_id="box-v2",
                target="template",
                operation="update",
                template=_template("box").model_copy(
                    update={
                        "annotation_type": "segment",
                        "component_config": {"components": ["segment"]},
                    }
                ),
            ),
        )
        _reject(
            lambda: upgrade_plan(
                session, UpgradeProjectTemplateParams(request_id="upgrade", project_id=project.id)
            ),
            "run the media probe",
        )


def test_review_rechecks_locked_media_after_probe_drift(db: Database) -> None:
    """Approval cannot reuse a stale duration after the locked source probe changes."""
    segment_source(db)
    _, tasks = segment_project(db, "group")
    with db.session() as session:
        _save(session, tasks[0], segment_annotation(tasks[0]))
        submit_task(session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "local")
        version = session.get(VersionRow, "catalog-source")
        assert version is not None
        version.manifest = [
            {
                **raw,
                "metadata": {"media_probe": {"duration_ms": 4000, "codec": "pcm_s16le"}},
            }
            for raw in version.manifest
        ]
        with pytest.raises(ValidationError, match="media_duration_ms"):
            review_task(
                session,
                ReviewTaskParams(
                    request_id="review",
                    task_id=tasks[0].id,
                    revision_id=require_task(session, tasks[0].id).latest_revision_id or "",
                    decision="approve",
                ),
                "local",
            )


def test_native_import_rejects_bad_media_before_batch_insert(db: Database) -> None:
    """Native JSONL batch validation uses source probes before writing any annotation facts."""
    segment_source(db)
    record = segment_annotation(
        ProductionTask(id="t", project_id="p", package_id="pk", sample_id="sample-0"), duration=4000
    )
    request = AnnotationImportRequest(
        version_id="catalog-source",
        batch=AnnotationBatch(annotations=(record,)),
        idempotency_key="bad-segments",
    )
    with db.session() as session:
        _reject(
            lambda: import_annotations_in_session(session, "catalog-data", request),
            "media_duration_ms",
        )
        assert session.scalar(select(AnnotationBatchRow)) is None


def test_template_min_max_counts_segments(db: Database) -> None:
    """The locked min/max rule counts media segments, including reviewed empty and duplicates."""
    segment_source(db)
    _, tasks = segment_project(db)
    empty = segment_annotation(tasks[0]).model_copy(update={"segments": ()})
    with db.session() as session:
        _reject(lambda: _save(session, tasks[0], empty), "count")
        too_many = segment_annotation(tasks[0]).model_copy(
            update={
                "segments": tuple(
                    AnnotationSegment(category="a", start_ms=0, end_ms=1, attributes={"note": "x"})
                    for _ in range(6)
                )
            }
        )
        _reject(lambda: _save(session, tasks[0], too_many), "count")


def test_max_one_allows_one_segment_with_classification(db: Database) -> None:
    """FIX1 repro: one segment plus one label is legal when max_annotations is one."""
    segment_source(db)
    _, tasks = segment_project(db, rules={"min_annotations": 1, "max_annotations": 1})
    annotation = segment_annotation(tasks[0]).model_copy(
        update={"labels": ("a",), "segments": (segment_annotation(tasks[0]).segments or ())[:1]}
    )
    with db.session() as session:
        try:
            _save(session, tasks[0], annotation)
            result = submit_task(
                session, SubmitTaskParams(request_id="submit-max-one", task_id=tasks[0].id), "local"
            )
        except ValidationError as error:
            message = "FIX1 max-one record must save and submit"
            raise AssertionError(message) from error
        assert result.state == "approved"


def test_min_two_rejects_one_segment_with_classification(db: Database) -> None:
    """FIX1 repro: a classification label cannot fill the second required segment."""
    segment_source(db)
    _, tasks = segment_project(db, rules={"min_annotations": 2, "max_annotations": 5})
    annotation = segment_annotation(tasks[0]).model_copy(
        update={"labels": ("a",), "segments": (segment_annotation(tasks[0]).segments or ())[:1]}
    )
    with db.session() as session:
        _reject(lambda: _save(session, tasks[0], annotation), "count")


def test_segment_boundaries_ignore_zero_or_multiple_classification_labels(db: Database) -> None:
    """Zero, two and three segments are counted exactly, even with three labels."""
    segment_source(db)
    _, tasks = segment_project(db, rules={"min_annotations": 1, "max_annotations": 2})
    base = segment_annotation(tasks[0]).model_copy(update={"labels": ("a", "b", "c")})
    with db.session() as session:
        _reject(lambda: _save(session, tasks[0], base.model_copy(update={"segments": ()})), "count")
        too_many = base.model_copy(
            update={
                "segments": (
                    *(base.segments or ()),
                    AnnotationSegment(
                        category="a", start_ms=2000, end_ms=3000, attributes={"note": "多段"}
                    ),
                )
            }
        )
        _reject(lambda: _save(session, tasks[0], too_many), "count")
        _save(session, tasks[0], base)
        result = submit_task(
            session, SubmitTaskParams(request_id="submit-two", task_id=tasks[0].id), "local"
        )
        assert result.state == "approved"


def test_non_segment_mixed_template_still_counts_all_enabled_components() -> None:
    """Legacy box+classification keeps the previous sum rule and rejects one of each at max one."""
    template = ProductionTemplate(
        id="legacy",
        name="legacy",
        annotation_type="box",
        component_config={"components": ["box", "classification"]},
        validation_rules={"max_annotations": 1},
    )
    annotation = AnnotationRecord(
        sample_id="image",
        annotator_id="ann",
        labels=("a",),
        boxes=(AnnotationBox(category="a", x1=0, y1=0, x2=1, y2=1),),
    )
    _reject(lambda: validate_template_content(template, annotation), "count")


def test_segment_rejects_undefined_spatial_and_text_combinations() -> None:
    """Only classification may be combined with the media timeline component."""
    for kind in ("box", "polygon", "keypoints", "text_span"):
        with pytest.raises(ValueError, match="only segment"):
            ProductionTemplate(
                id="bad",
                name="bad",
                annotation_type="segment",
                component_config={"components": ["segment", kind]},
            )
