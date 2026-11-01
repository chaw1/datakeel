# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native keypoint imports convert size and EXIF frames without moving missing points."""

import pytest

from datakeel.core.annotation_models import (
    AnnotationKeypoint,
    AnnotationRecord,
    AnnotationSkeleton,
)
from datakeel.core.image_orientation import ImageGeometry, to_display
from datakeel.storage.prediction_frames import upright_import


@pytest.mark.parametrize("orientation", [6, 8])
def test_native_jsonl_converts_keypoints_and_size_to_upright(orientation: int) -> None:
    """Stored-frame native records keep every positioned state and ID through EXIF conversion."""
    geometry = ImageGeometry(orientation=orientation, stored_width=100, stored_height=80)
    record = AnnotationRecord(
        sample_id="s",
        annotator_id="a",
        keypoints=(
            AnnotationSkeleton(
                category="person",
                points=(
                    AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
                    AnnotationKeypoint(id="neck", x=30, y=40, state="occluded"),
                    AnnotationKeypoint(id="wrist", state="missing"),
                ),
            ),
        ),
        image_width=100,
        image_height=80,
    )
    upright = upright_import(record, geometry, None, normalized=False)
    assert (upright.image_width, upright.image_height) == (geometry.width, geometry.height)
    [skeleton] = list(upright.keypoints or ())
    assert (skeleton.points[0].x, skeleton.points[0].y) == to_display(geometry, 10, 20)
    assert (skeleton.points[1].x, skeleton.points[1].y) == to_display(geometry, 30, 40)
    assert skeleton.points[2].state == "missing"
    assert skeleton.points[2].x is None


def test_native_size_rescaling_applies_to_every_positioned_keypoint() -> None:
    """A declared size change scales both states and the public dimensions together."""
    record = AnnotationRecord(
        sample_id="s",
        annotator_id="a",
        keypoints=(
            AnnotationSkeleton(
                category="person",
                points=(
                    AnnotationKeypoint(id="nose", x=10, y=20, state="visible"),
                    AnnotationKeypoint(id="neck", x=30, y=40, state="occluded"),
                    AnnotationKeypoint(id="wrist", state="missing"),
                ),
            ),
        ),
        image_width=100,
        image_height=80,
    )
    rescaled = upright_import(
        record,
        ImageGeometry(stored_width=200, stored_height=160),
        "display",
        normalized=True,
    )
    [skeleton] = list(rescaled.keypoints or ())
    assert (skeleton.points[0].x, skeleton.points[0].y) == (20, 40)
    assert (skeleton.points[1].x, skeleton.points[1].y) == (60, 80)
    assert skeleton.points[2].state == "missing"
