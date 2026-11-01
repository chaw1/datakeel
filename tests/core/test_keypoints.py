# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Skeleton models preserve tri-state semantics, template identity and EXIF geometry."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError as SchemaValidationError

from datakeel.core.annotation_models import (
    AnnotationKeypoint,
    AnnotationRecord,
    AnnotationSkeleton,
)
from datakeel.core.errors import ValidationError
from datakeel.core.image_orientation import ImageGeometry, display_record, to_display
from datakeel.core.keypoint_models import KeypointDefinition, SkeletonDefinition
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.production_keypoints import (
    normalize_keypoints,
    validate_keypoints,
)


def _reject(call: Callable[[], object], match: str) -> None:
    message = None
    try:
        call()
    except (ValidationError, SchemaValidationError) as error:
        message = str(error)
    if message is None:
        text = "Expected keypoint validation to reject the input"
        raise AssertionError(text)
    assert match in message


def _schema() -> SkeletonDefinition:
    return SkeletonDefinition(
        points=(
            KeypointDefinition(id="nose", name="Nose", required=True),
            KeypointDefinition(id="neck", name="Neck"),
            KeypointDefinition(id="wrist", name="Wrist"),
        ),
        edges=(("nose", "neck"), ("neck", "wrist")),
    )


def _template(schema: SkeletonDefinition | None = None) -> ProductionTemplate:
    return ProductionTemplate(
        id="pose",
        name="Pose",
        annotation_type="keypoints",
        keypoint_schema=schema if schema is not None else _schema(),
    )


def _record(points: tuple[AnnotationKeypoint, ...]) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id="image",
        annotator_id="ann",
        keypoints=(AnnotationSkeleton(category="person", points=points),),
        image_width=100,
        image_height=80,
    )


def test_schema_rejects_duplicate_ids_bad_edges_and_legacy_placeholder_writes() -> None:
    """Invalid topology and unreadable legacy writes fail explicitly."""
    with pytest.raises(SchemaValidationError, match="unique"):
        SkeletonDefinition(
            points=(
                KeypointDefinition(id="same", name="One"),
                KeypointDefinition(id="same", name="Two"),
            )
        )
    with pytest.raises(SchemaValidationError, match="edges"):
        SkeletonDefinition(
            points=(KeypointDefinition(id="one", name="One"),), edges=(("one", "one"),)
        )
    legacy = ProductionTemplate(id="old", name="Old", annotation_type="keypoints")
    with pytest.raises(ValidationError, match="upgrade"):
        validate_keypoints(legacy, _record(()), complete=False)


def test_point_states_require_the_documented_coordinate_shape() -> None:
    """Missing has no coordinates; visible and occluded require both, including core zero."""
    _reject(lambda: AnnotationKeypoint(id="nose", x=0, y=0, state="missing"), "must not carry")
    with pytest.raises(SchemaValidationError, match="require both"):
        AnnotationKeypoint(id="nose", x=1, state="occluded")
    point = AnnotationKeypoint(id="nose", x=0, y=0, state="visible")
    assert (point.x, point.y) == (0, 0)


def test_new_save_aligns_by_id_and_appends_new_points_as_missing() -> None:
    """Input order never changes template order and absent points become missing."""
    record = _record(
        (
            AnnotationKeypoint(id="wrist", x=30, y=40, state="occluded"),
            AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
        )
    )
    normalized = normalize_keypoints(_template(), record)
    [skeleton] = list(normalized.keypoints or ())
    assert [point.id for point in skeleton.points] == ["nose", "neck", "wrist"]
    assert [point.state for point in skeleton.points] == ["visible", "missing", "occluded"]
    validate_keypoints(_template(), normalized, complete=False)
    validate_keypoints(_template(), normalized, complete=True)


def test_draft_allows_partial_but_submit_rejects_required_and_all_missing() -> None:
    """Autosave accepts partial work while submit enforces instance completeness."""
    missing = _record((AnnotationKeypoint(id="wrist", state="missing"),))
    normalized = normalize_keypoints(_template(), missing)
    validate_keypoints(_template(), normalized, complete=False)
    _reject(lambda: validate_keypoints(_template(), normalized, complete=True), "at least one")
    required_missing = normalize_keypoints(
        _template(),
        _record((AnnotationKeypoint(id="wrist", x=1, y=1, state="visible"),)),
    )
    with pytest.raises(ValidationError, match="required"):
        validate_keypoints(_template(), required_missing, complete=True)
    optional_only = _template(
        _schema().model_copy(
            update={
                "points": tuple(
                    point.model_copy(update={"required": False}) for point in _schema().points
                )
            }
        )
    )
    with pytest.raises(ValidationError, match="at least one"):
        validate_keypoints(optional_only, normalized, complete=True)


def test_unknown_duplicate_and_out_of_bounds_points_are_rejected() -> None:
    """Unknown IDs, duplicate IDs and coordinates outside the image cannot be saved."""
    for points in (
        (
            AnnotationKeypoint(id="unknown", x=1, y=1, state="visible"),
            AnnotationKeypoint(id="nose", x=1, y=1, state="visible"),
        ),
        (
            AnnotationKeypoint(id="nose", x=1, y=1, state="visible"),
            AnnotationKeypoint(id="nose", x=2, y=2, state="visible"),
        ),
        (AnnotationKeypoint(id="nose", x=101, y=1, state="visible"),),
    ):
        with pytest.raises(ValidationError):
            validate_keypoints(_template(), _record(points), complete=False)


def test_old_record_serialization_does_not_gain_a_null_keypoints_field() -> None:
    """The existing four components retain their previous JSON shape."""
    record = AnnotationRecord(sample_id="s", annotator_id="a", labels=())
    assert "keypoints" not in record.model_dump(mode="json")


@pytest.mark.parametrize("orientation", range(1, 9))
def test_exif_moves_positioned_points_and_preserves_missing(orientation: int) -> None:
    """Every EXIF orientation transforms both positioned states and leaves missing alone."""
    geometry = ImageGeometry(orientation=orientation, stored_width=100, stored_height=80)
    record = _record(
        (
            AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
            AnnotationKeypoint(id="neck", x=30, y=40, state="occluded"),
            AnnotationKeypoint(id="wrist", state="missing"),
        )
    )
    [skeleton] = list(display_record(record, geometry).keypoints or ())
    assert (skeleton.points[0].x, skeleton.points[0].y) == to_display(geometry, 10, 20)
    assert (skeleton.points[1].x, skeleton.points[1].y) == to_display(geometry, 30, 40)
    original = record.keypoints[0].points[2] if record.keypoints is not None else None
    assert skeleton.points[2] == original
