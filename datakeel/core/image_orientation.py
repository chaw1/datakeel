# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upright ("display") image geometry derived from EXIF Orientation without touching pixels.

Stored pixels keep their original order; the platform shows, annotates, imports and exports
coordinates in the frame obtained after applying EXIF Orientation (tag 274, values 1-8,
mirrors included), which is what browsers, Pillow ``ImageOps.exif_transpose``, Ultralytics and
CVAT use. Coordinates are continuous pixel-edge coordinates: ``0..width`` and ``0..height``.
"""

from typing import Literal

from pydantic import Field

from datakeel.core.annotation_models import (
    AnnotationBox,
    AnnotationPoint,
    AnnotationPolygon,
    AnnotationRecord,
)
from datakeel.core.models import BoundaryModel

CoordinateFrame = Literal["display", "stored"]
ORIENTATION_TAG = 274
_SWAPPED = frozenset({5, 6, 7, 8})
# Pillow ImageOps.exif_transpose names for each EXIF value, recorded in lineage.
TRANSFORMS = {
    1: "none",
    2: "flip_left_right",
    3: "rotate_180",
    4: "flip_top_bottom",
    5: "transpose",
    6: "rotate_270",
    7: "transverse",
    8: "rotate_90",
}


def orientation_value(raw: object) -> int:
    """Read one EXIF Orientation value; missing or out-of-range values mean upright (1)."""
    if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= 8:  # noqa: PLR2004
        return raw
    return 1


class ImageGeometry(BoundaryModel):
    """Stored pixel size plus the EXIF orientation that turns it upright."""

    orientation: int = Field(default=1, ge=1, le=8)
    stored_width: int = Field(gt=0)
    stored_height: int = Field(gt=0)

    @property
    def swapped(self) -> bool:
        """Report whether the upright frame exchanges width and height."""
        return self.orientation in _SWAPPED

    @property
    def width(self) -> int:
        """Return the upright width, which is the public ``image_width``."""
        return self.stored_height if self.swapped else self.stored_width

    @property
    def height(self) -> int:
        """Return the upright height, which is the public ``image_height``."""
        return self.stored_width if self.swapped else self.stored_height

    @property
    def transform(self) -> str:
        """Name the Pillow transpose that produces the upright pixels."""
        return TRANSFORMS[self.orientation]


def to_display(geometry: ImageGeometry, x: float, y: float) -> tuple[float, float]:
    """Map a stored-frame point to the upright frame."""
    width, height = geometry.stored_width, geometry.stored_height
    mapping = {
        1: (x, y),
        2: (width - x, y),
        3: (width - x, height - y),
        4: (x, height - y),
        5: (y, x),
        6: (height - y, x),
        7: (height - y, width - x),
        8: (y, width - x),
    }
    return mapping[geometry.orientation]


def to_stored(geometry: ImageGeometry, x: float, y: float) -> tuple[float, float]:
    """Map an upright-frame point back to stored pixels; the inverse of ``to_display``."""
    width, height = geometry.stored_width, geometry.stored_height
    mapping = {
        1: (x, y),
        2: (width - x, y),
        3: (width - x, height - y),
        4: (x, height - y),
        5: (y, x),
        6: (y, height - x),
        7: (width - y, height - x),
        8: (width - y, x),
    }
    return mapping[geometry.orientation]


def _span(first: float, second: float, *, ordered: bool) -> tuple[float, float]:
    low, high = sorted((first, second))
    return (low, high) if ordered else (high, low)


def _box(geometry: ImageGeometry, box: AnnotationBox) -> AnnotationBox:
    first = to_display(geometry, box.x1, box.y1)
    second = to_display(geometry, box.x2, box.y2)
    # Keep deliberately inverted boxes inverted so rule review still sees them.
    x_source, y_source = (
        (box.y2 >= box.y1, box.x2 >= box.x1)
        if geometry.swapped
        else (box.x2 >= box.x1, box.y2 >= box.y1)
    )
    x1, x2 = _span(first[0], second[0], ordered=x_source)
    y1, y2 = _span(first[1], second[1], ordered=y_source)
    return box.model_copy(update={"x1": x1, "y1": y1, "x2": x2, "y2": y2})


def _polygon(geometry: ImageGeometry, polygon: AnnotationPolygon) -> AnnotationPolygon:
    points = tuple(
        AnnotationPoint(x=x, y=y)
        for x, y in (to_display(geometry, point.x, point.y) for point in polygon.points)
    )
    return polygon.model_copy(update={"points": points})


def display_record(record: AnnotationRecord, geometry: ImageGeometry) -> AnnotationRecord:
    """Re-express a stored-frame annotation in the upright frame; identity for orientation 1."""
    if geometry.orientation == 1:
        return record
    return record.model_copy(
        update={
            "boxes": tuple(_box(geometry, box) for box in record.boxes)
            if record.boxes is not None
            else None,
            "polygons": tuple(_polygon(geometry, polygon) for polygon in record.polygons)
            if record.polygons is not None
            else None,
            "image_width": geometry.width if record.image_width is not None else None,
            "image_height": geometry.height if record.image_height is not None else None,
        }
    )


class CoordinateConversion(BoundaryModel):
    """Trace a read-time conversion of a stored-frame annotation into the upright frame."""

    from_frame: CoordinateFrame = "stored"
    to_frame: CoordinateFrame = "display"
    orientation: int = Field(ge=1, le=8)
    transform: str
    stored_width: int = Field(gt=0)
    stored_height: int = Field(gt=0)


def conversion(geometry: ImageGeometry) -> CoordinateConversion:
    """Describe the exact stored-to-upright transform applied to one record."""
    return CoordinateConversion(
        orientation=geometry.orientation,
        transform=geometry.transform,
        stored_width=geometry.stored_width,
        stored_height=geometry.stored_height,
    )
