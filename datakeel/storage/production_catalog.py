# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and validate production vocabularies, templates and approved model definitions."""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.production_catalog_models import LabelSet, ProductionModel, ProductionTemplate
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionTemplateRow,
)

if TYPE_CHECKING:
    from datakeel.core.production_models import Project


def label_set_row(
    session: Session,
    identifier: str,
    version: int,
    *,
    lock: bool = False,
) -> ProductionLabelSetRow:
    """Resolve an exact vocabulary identity without silently selecting another version."""
    statement = select(ProductionLabelSetRow).where(
        ProductionLabelSetRow.label_set_id == identifier,
        ProductionLabelSetRow.version == version,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(statement)
    if row is None:
        message = "Label set version was not found"
        raise NotFoundError(message)
    return row


def require_label_set(
    session: Session, identifier: str, version: int, *, published: bool = True
) -> LabelSet:
    """Return a frozen vocabulary, normally requiring an approved published version."""
    row = label_set_row(session, identifier, version)
    value = LabelSet.model_validate(row.payload)
    if published and not value.published:
        message = "Projects require a published label set version"
        raise ValidationError(message)
    return value


def require_template(session: Session, identifier: str) -> ProductionTemplate:
    """Reject missing or archived templates before they are attached to a project."""
    row = session.get(ProductionTemplateRow, identifier)
    if row is None:
        message = "Annotation template was not found"
        raise NotFoundError(message)
    value = ProductionTemplate.model_validate(row.payload)
    if value.archived:
        message = "Annotation template is archived"
        raise ValidationError(message)
    return value


def require_model(session: Session, identifier: str) -> ProductionModel:
    """Resolve the currently approved offline model configuration."""
    row = session.get(ProductionModelRow, identifier)
    if row is None:
        message = "Prelabel model was not found"
        raise NotFoundError(message)
    return ProductionModel.model_validate(row.payload)


def annotation_categories(annotation: AnnotationRecord) -> tuple[str, ...]:
    """Count individual categorical, box and span annotations with their exact labels."""
    return (
        *(annotation.labels or ()),
        *(box.category for box in annotation.boxes or ()),
        *(span.category for span in annotation.spans or ()),
    )


def normalize_annotation(
    session: Session,
    project: "Project",
    annotation: AnnotationRecord,
) -> AnnotationRecord:
    """Canonicalize current display names and stable identities to version-pinned label ids."""
    labels = require_label_set(session, project.label_set_id, project.label_set_version)
    identities = {value: label.id for label in labels.labels for value in (label.id, label.name)}
    return annotation.model_copy(
        update={
            "labels": tuple(identities.get(value, value) for value in annotation.labels)
            if annotation.labels is not None
            else None,
            "boxes": tuple(
                box.model_copy(update={"category": identities.get(box.category, box.category)})
                for box in annotation.boxes
            )
            if annotation.boxes is not None
            else None,
            "spans": tuple(
                span.model_copy(update={"category": identities.get(span.category, span.category)})
                for span in annotation.spans
            )
            if annotation.spans is not None
            else None,
        }
    )


def validate_annotation(session: Session, project: "Project", annotation: AnnotationRecord) -> None:
    """Validate labels, geometry and the project's explicit reusable template rules."""
    labels = require_label_set(session, project.label_set_id, project.label_set_version)
    allowed = {value for label in labels.labels for value in (label.id, label.name)}
    if not set(annotation_categories(annotation)) <= allowed:
        message = "Annotation categories must belong to the project's published label set"
        raise ValidationError(message)
    _validate_geometry(annotation)
    if project.template_id is not None:
        _validate_template(require_template(session, project.template_id), annotation)


def _validate_geometry(annotation: AnnotationRecord) -> None:
    for box in annotation.boxes or ():
        if box.x1 < 0 or box.y1 < 0 or box.x2 <= box.x1 or box.y2 <= box.y1:
            message = "Annotation boxes require positive area and nonnegative pixel coordinates"
            raise ValidationError(message)
        if (annotation.image_width is not None and box.x2 > annotation.image_width) or (
            annotation.image_height is not None and box.y2 > annotation.image_height
        ):
            message = "Annotation box is outside image bounds"
            raise ValidationError(message)
    for span in annotation.spans or ():
        if (
            span.start < 0
            or span.end <= span.start
            or (annotation.text_length is not None and span.end > annotation.text_length)
        ):
            message = "Annotation span is outside text bounds"
            raise ValidationError(message)


def _validate_template(template: ProductionTemplate, annotation: AnnotationRecord) -> None:
    content = {
        "box": annotation.boxes,
        "classification": annotation.labels,
        "text_span": annotation.spans,
    }
    if template.annotation_type not in content:
        message = "This template's content type is not supported by the current core schema"
        raise ValidationError(message)
    if content[template.annotation_type] is None or any(
        value is not None for kind, value in content.items() if kind != template.annotation_type
    ):
        message = "Annotation content does not match the project's template type"
        raise ValidationError(message)
    count = len(content[template.annotation_type] or ())
    minimum = template.validation_rules.get("min_annotations", 0)
    maximum = template.validation_rules.get("max_annotations", 100000)
    if (
        not isinstance(minimum, int)
        or not isinstance(maximum, int)
        or not minimum <= count <= maximum
    ):
        message = "Annotation count violates the template's validation rules"
        raise ValidationError(message)
