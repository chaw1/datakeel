# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and validate production vocabularies, templates and approved model definitions."""

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.production_attributes import validate_attributes
from datakeel.core.production_catalog_models import LabelSet, ProductionModel, ProductionTemplate
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionTemplateRow,
)
from datakeel.storage.production_template_versions import locked_template

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
        *(polygon.category for polygon in annotation.polygons or ()),
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
            "polygons": tuple(
                polygon.model_copy(
                    update={"category": identities.get(polygon.category, polygon.category)}
                )
                for polygon in annotation.polygons
            )
            if annotation.polygons is not None
            else None,
        }
    )


def validate_annotation(
    session: Session, project: "Project", annotation: AnnotationRecord, *, complete: bool = True
) -> None:
    """Validate labels, geometry and the project's locked template rules and attribute fields.

    ``complete`` also requires every required attribute; model drafts are only type-checked.
    """
    labels = require_label_set(session, project.label_set_id, project.label_set_version)
    allowed = {value for label in labels.labels for value in (label.id, label.name)}
    if not set(annotation_categories(annotation)) <= allowed:
        message = "Annotation categories must belong to the project's published label set"
        raise ValidationError(message)
    _validate_geometry(annotation)
    template = locked_template(session, project)
    if template is not None:
        validate_template_content(template, annotation)
        validate_attributes(template.attributes, annotation, complete=complete)


def require_complete_attributes(
    session: Session, project: "Project", annotation: AnnotationRecord
) -> None:
    """Recheck a submitted head against the project's locked template attribute fields."""
    template = locked_template(session, project)
    if template is not None:
        validate_attributes(template.attributes, annotation)


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
    for polygon in annotation.polygons or ():
        points = polygon.points
        if any(
            point.x < 0
            or point.y < 0
            or (annotation.image_width is not None and point.x > annotation.image_width)
            or (annotation.image_height is not None and point.y > annotation.image_height)
            for point in points
        ):
            message = "Annotation polygon is outside image bounds"
            raise ValidationError(message)
        area = sum(
            left.x * right.y - right.x * left.y
            for left, right in zip(points, (*points[1:], points[0]), strict=True)
        )
        if len({(point.x, point.y) for point in points}) != len(points) or area == 0:
            message = "Annotation polygons require distinct vertices and nonzero area"
            raise ValidationError(message)


def validate_template_content(template: ProductionTemplate, annotation: AnnotationRecord) -> None:
    """Check enabled components, single-select labels and the annotation-count rules."""
    content = {
        "box": annotation.boxes,
        "classification": annotation.labels,
        "text_span": annotation.spans,
        "polygon": annotation.polygons,
    }
    if template.annotation_type not in content:
        message = "This template's content type is not supported by the current core schema"
        raise ValidationError(message)
    configured = template.component_config.get("components")
    enabled = (
        {value for value in configured if isinstance(value, str)}
        if isinstance(configured, list)
        else {template.annotation_type}
    )
    if not any(content[kind] is not None for kind in enabled) or any(
        value is not None for kind, value in content.items() if kind not in enabled
    ):
        message = "Annotation content does not match the project's template type"
        raise ValidationError(message)
    count = sum(len(content[kind] or ()) for kind in enabled)
    if (
        "classification" in enabled
        and template.component_config.get("label_mode") == "single"
        and len(annotation.labels or ()) > 1
    ):
        message = "Single-select classification templates accept at most one label"
        raise ValidationError(message)
    minimum = template.validation_rules.get("min_annotations", 0)
    maximum = template.validation_rules.get("max_annotations", 100000)
    if (
        not isinstance(minimum, int)
        or not isinstance(maximum, int)
        or not minimum <= count <= maximum
    ):
        message = "Annotation count violates the template's validation rules"
        raise ValidationError(message)
