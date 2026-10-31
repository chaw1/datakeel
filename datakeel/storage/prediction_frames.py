# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Decide which pixel frame imported predictions and annotations use and bring them upright.

YOLO normalized coordinates are read against the upright size, as Ultralytics applies EXIF
Orientation before training and inference. COCO declares each image's width and height: equal
to the upright size means upright coordinates; equal only to the stored size (a 90-degree
orientation) means stored coordinates, converted here. A square image cannot tell the two
apart and defaults to upright. ``coordinate_frame`` from the caller overrides the inference.
"""

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.image_orientation import CoordinateFrame, ImageGeometry, display_record
from datakeel.core.production_prediction_models import PredictionSample


def prediction_frame(
    declared: CoordinateFrame | None,
    width: float | None,
    height: float | None,
    sample: PredictionSample,
) -> CoordinateFrame:
    """Return the explicit frame, else infer it from the declared image size."""
    if declared is not None:
        return declared
    geometry = sample.geometry
    if geometry is None or width is None or height is None:
        return "display"
    if (width, height) == (geometry.width, geometry.height):
        return "display"
    if (width, height) == (geometry.stored_width, geometry.stored_height):
        return "stored"
    return "display"


def frame_size(
    sample: PredictionSample, frame: CoordinateFrame
) -> tuple[float | None, float | None]:
    """Return the recorded image size in the chosen frame."""
    if frame == "stored" and sample.geometry is not None:
        return float(sample.geometry.stored_width), float(sample.geometry.stored_height)
    return sample.width, sample.height


def upright_prediction(
    record: AnnotationRecord, sample: PredictionSample, frame: CoordinateFrame
) -> AnnotationRecord:
    """Convert a stored-frame prediction to the upright frame every revision uses."""
    if frame == "display" or sample.geometry is None:
        return record
    return display_record(record, sample.geometry)


def _rescaled(record: AnnotationRecord, width: float, height: float) -> AnnotationRecord:
    if record.image_width is None or record.image_height is None:
        return record
    x_scale, y_scale = width / record.image_width, height / record.image_height
    return record.model_copy(
        update={
            "boxes": tuple(
                box.model_copy(
                    update={
                        "x1": box.x1 * x_scale,
                        "x2": box.x2 * x_scale,
                        "y1": box.y1 * y_scale,
                        "y2": box.y2 * y_scale,
                    }
                )
                for box in record.boxes
            )
            if record.boxes is not None
            else None,
            "image_width": width,
            "image_height": height,
        }
    )


def upright_import(
    record: AnnotationRecord,
    geometry: ImageGeometry | None,
    declared: CoordinateFrame | None,
    *,
    normalized: bool,
) -> AnnotationRecord:
    """Bring one imported dataset annotation into the upright frame.

    ``normalized`` (YOLO) coordinates are relative to the upright image, so a record decoded
    with any other size is rescaled to the upright size; COCO and native records use the
    width/height inference of ``prediction_frame``.
    """
    if geometry is None:
        return record
    sample = PredictionSample(
        id=record.sample_id,
        filename=record.sample_id,
        width=geometry.width,
        height=geometry.height,
        geometry=geometry,
    )
    if normalized:
        if (declared or "display") == "stored":
            stored = _rescaled(record, geometry.stored_width, geometry.stored_height)
            return display_record(stored, geometry)
        return _rescaled(record, geometry.width, geometry.height)
    frame = prediction_frame(declared, record.image_width, record.image_height, sample)
    return upright_prediction(record, sample, frame)
