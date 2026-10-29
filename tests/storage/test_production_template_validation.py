# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reusable production template rules apply equally to human and model annotation content."""

import pytest

from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    PublishLabelSetParams,
)
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord, AnnotationSpan
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.production_catalog_models import ProductionLabel, ProductionTemplate
from datakeel.storage.database import Database
from datakeel.storage.production_catalog import (
    annotation_categories,
    require_label_set,
    validate_annotation,
)
from datakeel.storage.production_catalog_changes import (
    create_label_set,
    manage_template,
    publish_label_set,
)
from datakeel.storage.production_catalog_impact import validate_migration
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionProjectRow
from datakeel.storage.production_tasks import require_task
from tests.storage.production_catalog_fixtures import catalog_project


@pytest.mark.parametrize("kind", ["box", "classification", "text_span"])
def test_templates_validate_expected_content_and_cardinality(db: Database, kind: str) -> None:
    """The template accepts its supported core shape and rejects missing or excessive content."""
    fixture = catalog_project(db)
    template = ProductionTemplate.model_validate(
        {
            "id": "template",
            "name": "Template",
            "annotation_type": kind,
            "validation_rules": {"min_annotations": 1, "max_annotations": 1},
        }
    )
    annotations = {
        "box": AnnotationRecord(
            sample_id="sample-0",
            annotator_id="local",
            boxes=(AnnotationBox(category="a", x1=0, y1=0, x2=10, y2=10),),
        ),
        "classification": AnnotationRecord(
            sample_id="sample-0", annotator_id="local", labels=("a",)
        ),
        "text_span": AnnotationRecord(
            sample_id="sample-0",
            annotator_id="local",
            spans=(AnnotationSpan(category="a", start=0, end=1),),
            text_length=1,
        ),
    }
    project = fixture.project.model_copy(update={"template_id": template.id})
    with db.session() as session:
        manage_template(
            session,
            CreateLabelSetParams(request_id="template", target="template", template=template),
        )
        validate_annotation(session, project, annotations[kind])
        with pytest.raises(ValidationError, match="template type"):
            validate_annotation(
                session, project, AnnotationRecord(sample_id="sample-0", annotator_id="local")
            )
        empty = annotations[kind].model_copy(
            update={
                {"box": "boxes", "classification": "labels", "text_span": "spans"}[kind]: (),
            }
        )
        with pytest.raises(ValidationError, match="count"):
            validate_annotation(session, project, empty)


def test_future_template_types_are_objects_but_do_not_invent_core_content(db: Database) -> None:
    """Polygon/keypoint templates can be managed before their core content models are introduced."""
    fixture = catalog_project(db)
    with db.session() as session:
        template = ProductionTemplate(id="future", name="Polygon", annotation_type="polygon")
        manage_template(
            session, CreateLabelSetParams(request_id="future", target="template", template=template)
        )
        project = fixture.project.model_copy(update={"template_id": template.id})
        with pytest.raises(ValidationError, match="not supported"):
            validate_annotation(
                session, project, AnnotationRecord(sample_id="sample-0", annotator_id="local")
            )


def test_label_versions_require_known_and_nonoverlapping_migration_sources(db: Database) -> None:
    """Changing the catalog never allows unknown identities or contradictory source decisions."""
    catalog_project(db)
    with db.session() as session:
        before = require_label_set(session, "labels", 1)
        for migration in (
            [{"operation": "rename", "source_ids": ["unknown"], "target_ids": ["a"]}],
            [{"operation": "rename", "source_ids": ["a"], "target_ids": ["unknown"]}],
            [
                {"operation": "rename", "source_ids": ["a"], "target_ids": ["a"]},
                {"operation": "delete", "source_ids": ["a"], "strategy": "drop"},
            ],
        ):
            after = type(before).model_validate(
                {**before.model_dump(mode="json"), "version": 2, "migration": migration}
            )
            with pytest.raises(ValidationError):
                validate_migration(before, after)
        params = CreateLabelSetParams(request_id="v2", label_set_id="labels", labels=before.labels)
        draft = create_label_set(session, params)
        with pytest.raises(ConflictError, match="exists"):
            create_label_set(session, params.model_copy(update={"version": draft.version}))
        publication = PublishLabelSetParams(request_id="publish", label_set_id="labels", version=2)
        publish_label_set(session, publication)
        with pytest.raises(ConflictError, match="already published"):
            publish_label_set(session, publication)


def test_saved_display_names_and_ids_share_one_stable_annotation_identity(db: Database) -> None:
    """Human and model conventions cannot split one label into two apparent categories for P26."""
    fixture = catalog_project(db)
    with db.session() as session:
        create_label_set(
            session,
            CreateLabelSetParams(
                request_id="aliases",
                label_set_id="aliases",
                labels=(ProductionLabel(id="cat", name="Cat"),),
            ),
        )
        publish_label_set(
            session,
            PublishLabelSetParams(request_id="publish-aliases", label_set_id="aliases", version=1),
        )
        project = fixture.project.model_copy(update={"label_set_id": "aliases"})
        row = session.get(ProductionProjectRow, project.id)
        assert row is not None
        row.payload = project.model_dump(mode="json")
        task = require_task(session, fixture.tasks[0].id)
        first = append_revision(
            session,
            task,
            SaveRevisionParams(
                request_id="display-name",
                task_id=task.id,
                previous_revision_id=None,
                annotation=AnnotationRecord(
                    sample_id=task.sample_id,
                    annotator_id="local",
                    labels=("Cat",),
                    boxes=(AnnotationBox(category="Cat", x1=0, y1=0, x2=10, y2=10),),
                    spans=(AnnotationSpan(category="Cat", start=0, end=1),),
                ),
            ),
            "local",
        )
        assert annotation_categories(first.annotation) == ("cat", "cat", "cat")
        second = append_revision(
            session,
            task,
            SaveRevisionParams(
                request_id="stable-id",
                task_id=task.id,
                previous_revision_id=first.id,
                annotation=first.annotation,
            ),
            "local",
        )
        assert second.annotation == first.annotation
        assert second.previous_revision_id == first.id
