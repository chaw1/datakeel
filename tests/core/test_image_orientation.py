# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upright-frame geometry agrees with Pillow's EXIF transpose for all eight orientations."""

import pytest
from PIL import Image, ImageOps

from datakeel.core.annotation_models import (
    AnnotationBox,
    AnnotationPoint,
    AnnotationPolygon,
    AnnotationRecord,
)
from datakeel.core.image_orientation import (
    ImageGeometry,
    conversion,
    display_record,
    orientation_value,
    to_display,
    to_stored,
)

WIDTH, HEIGHT = 7, 4


def _oriented(orientation: int) -> Image.Image:
    image = Image.new("I", (WIDTH, HEIGHT))
    image.putdata([y * WIDTH + x for y in range(HEIGHT) for x in range(WIDTH)])
    image.getexif()[274] = orientation
    return image


@pytest.mark.parametrize("orientation", range(1, 9))
def test_every_stored_pixel_lands_where_pillow_puts_it(orientation: int) -> None:
    """Each stored pixel centre maps into the upright pixel that exif_transpose moves it to."""
    upright = ImageOps.exif_transpose(_oriented(orientation))
    geometry = ImageGeometry(orientation=orientation, stored_width=WIDTH, stored_height=HEIGHT)
    assert upright.size == (geometry.width, geometry.height)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            display_x, display_y = to_display(geometry, x + 0.5, y + 0.5)
            assert upright.getpixel((int(display_x), int(display_y))) == y * WIDTH + x
            assert to_stored(geometry, display_x, display_y) == (x + 0.5, y + 0.5)


@pytest.mark.parametrize("orientation", range(1, 9))
def test_boxes_polygons_and_size_move_with_the_pixels(orientation: int) -> None:
    """A box keeps covering the same pixels; polygon vertices and image size follow."""
    geometry = ImageGeometry(orientation=orientation, stored_width=WIDTH, stored_height=HEIGHT)
    record = AnnotationRecord(
        sample_id="s",
        annotator_id="a",
        image_width=WIDTH,
        image_height=HEIGHT,
        boxes=(AnnotationBox(category="c", x1=1, y1=1, x2=3, y2=2),),
        polygons=(
            AnnotationPolygon(
                category="c",
                points=(
                    AnnotationPoint(x=1, y=1),
                    AnnotationPoint(x=3, y=1),
                    AnnotationPoint(x=3, y=2),
                ),
            ),
        ),
    )
    upright = display_record(record, geometry)
    assert (upright.image_width, upright.image_height) == (geometry.width, geometry.height)
    [box] = list(upright.boxes or ())
    assert box.x1 < box.x2 and box.y1 < box.y2  # noqa: PT018
    covered = {
        (x, y)
        for x in range(WIDTH)
        for y in range(HEIGHT)
        if box.x1 <= to_display(geometry, x + 0.5, y + 0.5)[0] <= box.x2
        and box.y1 <= to_display(geometry, x + 0.5, y + 0.5)[1] <= box.y2
    }
    assert covered == {(1, 1), (2, 1)}
    [polygon] = list(upright.polygons or ())
    assert [(p.x, p.y) for p in polygon.points] == [
        to_display(geometry, 1, 1),
        to_display(geometry, 3, 1),
        to_display(geometry, 3, 2),
    ]


def test_identity_and_unknown_values_are_untouched() -> None:
    """Orientation 1 is the identity, and unreadable tags count as 1."""
    record = AnnotationRecord(sample_id="s", annotator_id="a", image_width=7, image_height=4)
    assert display_record(record, ImageGeometry(stored_width=7, stored_height=4)) is record
    assert [orientation_value(value) for value in (None, 0, 9, "6", True, 6)] == [1, 1, 1, 1, 1, 6]


def test_inverted_boxes_stay_inverted_and_unknown_size_stays_unknown() -> None:
    """Deliberately invalid boxes keep their inversion for rule review after conversion."""
    geometry = ImageGeometry(orientation=6, stored_width=10, stored_height=20)
    record = AnnotationRecord(
        sample_id="s",
        annotator_id="a",
        boxes=(AnnotationBox(category="c", x1=5, y1=2, x2=3, y2=9),),
    )
    [box] = list(display_record(record, geometry).boxes or ())
    assert box.x1 < box.x2  # stored y-extent was valid and becomes the upright x-extent
    assert box.y1 > box.y2  # stored x-extent was inverted and stays inverted
    upright = display_record(record, geometry)
    assert upright.image_width is None
    assert upright.image_height is None


def test_conversion_trace_names_the_pillow_transpose() -> None:
    """The recorded trace is enough to redo or undo the conversion."""
    trace = conversion(ImageGeometry(orientation=8, stored_width=4, stored_height=3))
    assert trace.model_dump() == {
        "from_frame": "stored",
        "to_frame": "display",
        "orientation": 8,
        "transform": "rotate_90",
        "stored_width": 4,
        "stored_height": 3,
    }
