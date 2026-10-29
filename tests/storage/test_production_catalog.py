# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog draft immutability, explicit migrations and exact latest-annotation impact."""

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    PublishLabelSetParams,
    RegisterModelParams,
    UpdateModelParams,
)
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord, AnnotationSpan
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.production_catalog_models import (
    LabelMigration,
    ProductionLabel,
    ProductionTemplate,
)
from datakeel.storage.database import Database
from datakeel.storage.production_catalog import (
    require_label_set,
    require_model,
    require_template,
    validate_annotation,
)
from datakeel.storage.production_catalog_changes import (
    create_label_set,
    manage_template,
    publish_label_set,
    save_model,
)
from datakeel.storage.production_catalog_impact import migration_impact, validate_migration
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from tests.storage.production_catalog_fixtures import catalog_project


def _version_two() -> CreateLabelSetParams:
    return CreateLabelSetParams(
        request_id="version-two",
        label_set_id="labels",
        labels=tuple(
            ProductionLabel(id=key, name=name)
            for key, name in (
                ("a", "renamed"),
                ("merged", "merged"),
                ("e1", "split one"),
                ("e2", "split two"),
            )
        ),
        migration=(
            LabelMigration(operation="rename", source_ids=("a",), target_ids=("a",)),
            LabelMigration(operation="delete", source_ids=("b",), strategy="drop"),
            LabelMigration(operation="merge", source_ids=("c", "d"), target_ids=("merged",)),
            LabelMigration(
                operation="split", source_ids=("e",), target_ids=("e1", "e2"), strategy="manual"
            ),
        ),
    )


def test_migration_counts_latest_annotation_instances_exactly(db: Database) -> None:
    """Renames/deletes/merges/splits count each affected box, span or class, excluding history."""
    fixture = catalog_project(db)
    with db.session() as session:
        _seed_migration_annotations(session, tuple(task.id for task in fixture.tasks))
        session.flush()
        draft = create_label_set(session, _version_two())
        assert (draft.affected_annotations, draft.affected_revisions) == (5, 2)
        published = publish_label_set(
            session,
            PublishLabelSetParams(
                request_id="publish-v2",
                label_set_id="labels",
                version=2,
            ),
        )
        assert (published.affected_annotations, published.affected_revisions) == (5, 2)
        assert migration_impact(session, require_label_set(session, "labels", 1), published) == (
            5,
            2,
        )
        session.commit()


def test_published_label_versions_reject_application_and_database_mutations(db: Database) -> None:
    """A published v1 cannot be edited or deleted, including alternate SQL paths."""
    catalog_project(db)
    with db.session() as session, pytest.raises(ConflictError, match="immutable"):
        create_label_set(
            session,
            CreateLabelSetParams(
                request_id="edit",
                label_set_id="labels",
                version=1,
                operation="update",
                labels=(ProductionLabel(id="a", name="changed"),),
            ),
        )
    for statement in (
        update(ProductionLabelSetRow).values(published=False),
        delete(ProductionLabelSetRow),
    ):
        with db.session() as session, pytest.raises(DBAPIError, match="immutable"):
            session.execute(statement)


def test_catalog_drafts_validate_trees_and_complete_migrations(db: Database) -> None:
    """Draft edits remain possible while missing migration decisions and cyclic labels fail."""
    catalog_project(db)
    with db.session() as session:
        for labels in (
            (ProductionLabel(id="x", name="x", parent_id="x"),),
            (ProductionLabel(id="x", name="x"), ProductionLabel(id="x", name="y")),
            (ProductionLabel(id="x", name="y"), ProductionLabel(id="y", name="z")),
        ):
            with pytest.raises(ValidationError):
                create_label_set(session, CreateLabelSetParams(request_id="bad", labels=labels))
            session.rollback()
        with pytest.raises(ValidationError, match="complete migration"):
            create_label_set(session, _version_two().model_copy(update={"migration": ()}))
        session.rollback()
        value = create_label_set(
            session,
            CreateLabelSetParams(
                request_id="draft",
                label_set_id="draft",
                labels=(ProductionLabel(id="x", name="x"),),
            ),
        )
        changed = create_label_set(
            session,
            CreateLabelSetParams(
                request_id="edit",
                operation="update",
                label_set_id="draft",
                version=1,
                labels=(ProductionLabel(id="x", name="changed"),),
            ),
        )
        assert changed.labels[0].name == "changed"
        with pytest.raises(ValidationError, match="published"):
            require_label_set(session, "draft", 1)
        before = require_label_set(session, "labels", 1)
        with pytest.raises(ValidationError, match="earlier"):
            validate_migration(before, before)
        create_label_set(
            session,
            CreateLabelSetParams(
                request_id="delete", operation="delete", label_set_id=value.id, version=1
            ),
        )
        session.flush()
        with pytest.raises(NotFoundError):
            require_label_set(session, value.id, 1)


def test_templates_and_models_use_optimistic_revisions(db: Database) -> None:
    """Template archive and model updates cannot replace a concurrent catalog revision."""
    fixture = catalog_project(db)
    template = ProductionTemplate(
        id="template", name="Boxes", validation_rules={"min_annotations": 1}
    )
    with db.session() as session:
        params = CreateLabelSetParams(request_id="template", target="template", template=template)
        assert manage_template(session, params).revision == 1
        assert require_template(session, template.id) == template
        with pytest.raises(ConflictError, match="already"):
            manage_template(session, params)
        updated = manage_template(session, params.model_copy(update={"operation": "update"}))
        assert updated.revision == 2
        with pytest.raises(ConflictError, match="revision"):
            manage_template(session, params.model_copy(update={"operation": "delete"}))
        archived = manage_template(
            session, params.model_copy(update={"operation": "delete", "template": updated})
        )
        assert archived.archived
        with pytest.raises(ValidationError, match="archived"):
            require_template(session, template.id)
        model = require_model(session, "fake")
        changed = save_model(
            session, UpdateModelParams(request_id="update", model=model, expected_revision=1)
        )
        assert changed.revision == 2
        with pytest.raises(ConflictError, match="revision"):
            save_model(
                session, UpdateModelParams(request_id="update", model=model, expected_revision=1)
            )
        with pytest.raises(ConflictError, match="exists"):
            save_model(session, RegisterModelParams(request_id="duplicate", model=model))
        with pytest.raises(NotFoundError):
            require_model(session, "absent")
        with pytest.raises(NotFoundError):
            require_template(session, "absent")
    assert fixture.project.template_id is None


@pytest.mark.parametrize(
    "annotation",
    [
        AnnotationRecord(sample_id="s", annotator_id="x", labels=("unknown",)),
        AnnotationRecord(
            sample_id="s",
            annotator_id="x",
            boxes=(AnnotationBox(category="a", x1=-1, y1=0, x2=1, y2=1),),
        ),
        AnnotationRecord(
            sample_id="s",
            annotator_id="x",
            boxes=(AnnotationBox(category="a", x1=0, y1=0, x2=101, y2=1),),
            image_width=100,
        ),
        AnnotationRecord(
            sample_id="s",
            annotator_id="x",
            spans=(AnnotationSpan(category="a", start=0, end=2),),
            text_length=1,
        ),
    ],
)
def test_annotation_rules_reject_unknown_labels_and_out_of_bounds_content(
    db: Database, annotation: AnnotationRecord
) -> None:
    """The same validation protects human saves, model imports and template-specific content."""
    fixture = catalog_project(db)
    with db.session() as session, pytest.raises(ValidationError):
        validate_annotation(session, fixture.project, annotation)


def _seed_migration_annotations(session: Session, task_ids: tuple[str, ...]) -> None:
    first, second = (require_task(session, task) for task in task_ids)
    previous = append_revision(
        session,
        first,
        SaveRevisionParams(
            request_id="old",
            task_id=first.id,
            previous_revision_id=None,
            annotation=AnnotationRecord(
                sample_id=first.sample_id,
                annotator_id="local",
                labels=("a", "b", "c", "d", "e"),
            ),
        ),
        "local",
    )
    append_revision(
        session,
        first,
        SaveRevisionParams(
            request_id="new",
            task_id=first.id,
            previous_revision_id=previous.id,
            annotation=AnnotationRecord(
                sample_id=first.sample_id, annotator_id="local", labels=("a", "c")
            ),
        ),
        "local",
    )
    append_revision(
        session,
        second,
        SaveRevisionParams(
            request_id="boxes",
            task_id=second.id,
            previous_revision_id=None,
            annotation=AnnotationRecord(
                sample_id=second.sample_id,
                annotator_id="local",
                boxes=(
                    AnnotationBox(category="a", x1=0, y1=0, x2=10, y2=10),
                    AnnotationBox(category="b", x1=20, y1=20, x2=30, y2=30),
                    AnnotationBox(category="a", x1=40, y1=40, x2=50, y2=50),
                ),
            ),
        ),
        "local",
    )
