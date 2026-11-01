# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Template-bound skeleton normalization and submit-time completeness rules."""

from datakeel.core.annotation_models import AnnotationKeypoint, AnnotationRecord, AnnotationSkeleton
from datakeel.core.errors import ValidationError
from datakeel.core.keypoint_models import KeypointDefinition, SkeletonDefinition
from datakeel.core.production_catalog_models import ProductionTemplate


def enabled_components(template: ProductionTemplate) -> set[str]:
    """Resolve the explicitly enabled components or the legacy primary component."""
    configured = template.component_config.get("components")
    if isinstance(configured, list):
        return {value for value in configured if isinstance(value, str)}
    return {template.annotation_type}


def require_schema(template: ProductionTemplate) -> SkeletonDefinition:
    """Reject legacy keypoint placeholders on every new write or schema-dependent export."""
    if template.keypoint_schema is None:
        message = "Keypoint templates require a typed keypoint_schema; upgrade the template first"
        raise ValidationError(message)
    return template.keypoint_schema


def normalize_keypoints(
    template: ProductionTemplate, annotation: AnnotationRecord
) -> AnnotationRecord:
    """Align each new skeleton by stable point ID and append newly introduced missing points."""
    if annotation.keypoints is None or "keypoints" not in enabled_components(template):
        return annotation
    schema = require_schema(template)
    skeletons = tuple(_normalize_skeleton(schema, skeleton) for skeleton in annotation.keypoints)
    return annotation.model_copy(update={"keypoints": skeletons})


def _normalize_skeleton(
    schema: SkeletonDefinition, skeleton: AnnotationSkeleton
) -> AnnotationSkeleton:
    identifiers = [point.id for point in skeleton.points]
    known = {point.id for point in schema.points}
    if len(set(identifiers)) != len(identifiers) or not set(identifiers) <= known:
        return skeleton
    by_id = {point.id: point for point in skeleton.points}
    points = tuple(
        by_id.get(definition.id, AnnotationKeypoint(id=definition.id, state="missing"))
        for definition in schema.points
    )
    return skeleton.model_copy(update={"points": points})


def validate_keypoints(
    template: ProductionTemplate, annotation: AnnotationRecord, *, complete: bool
) -> None:
    """Validate point identities, geometry and, only on submission, skeleton completeness."""
    if "keypoints" not in enabled_components(template):
        return
    schema = require_schema(template)
    definitions = {point.id: point for point in schema.points}
    for index, skeleton in enumerate(annotation.keypoints or (), start=1):
        _validate_skeleton_identity(skeleton, definitions, index)
        _validate_skeleton_bounds(annotation, skeleton, index)
        if complete:
            _require_complete_skeleton(skeleton, definitions, index)


def _validate_skeleton_identity(
    skeleton: AnnotationSkeleton, definitions: dict[str, KeypointDefinition], index: int
) -> None:
    identifiers = [point.id for point in skeleton.points]
    if len(set(identifiers)) != len(identifiers) or not set(identifiers) <= set(definitions):
        message = f"Skeleton {index} contains duplicate or unknown keypoint identities"
        raise ValidationError(message)


def _validate_skeleton_bounds(
    annotation: AnnotationRecord, skeleton: AnnotationSkeleton, index: int
) -> None:
    for point in skeleton.points:
        if point.state == "missing":
            continue
        if point.x is None or point.y is None:
            message = "Positioned keypoints require coordinates"
            raise ValidationError(message)
        if (
            point.x < 0
            or point.y < 0
            or (annotation.image_width is not None and point.x > annotation.image_width)
            or (annotation.image_height is not None and point.y > annotation.image_height)
        ):
            message = f"Skeleton {index} keypoint {point.id} is outside image bounds"
            raise ValidationError(message)


def _require_complete_skeleton(
    skeleton: AnnotationSkeleton, definitions: dict[str, KeypointDefinition], index: int
) -> None:
    points = {point.id: point for point in skeleton.points}
    positioned = [point for point in skeleton.points if point.state != "missing"]
    if not positioned:
        message = f"Skeleton {index} must contain at least one visible or occluded keypoint"
        raise ValidationError(message)
    required_missing: list[str] = []
    for identifier, definition in definitions.items():
        point = points.get(identifier)
        if definition.required and (point is None or point.state == "missing"):
            required_missing.append(identifier)
    if required_missing:
        message = f"Skeleton {index} is missing required keypoints: {', '.join(required_missing)}"
        raise ValidationError(message)
