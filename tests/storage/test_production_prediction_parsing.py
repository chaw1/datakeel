# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated COCO/YOLO partial errors and exact coordinate/provenance parsing."""

import json

import pytest

from datakeel.core.models import utcnow
from datakeel.core.production_catalog_models import LabelSet, PredictionFile, ProductionLabel
from datakeel.core.production_prediction_models import PredictionSample
from datakeel.storage.production_prediction_parsing import parse_coco, parse_yolo


def _labels() -> LabelSet:
    return LabelSet(
        id="labels",
        version=1,
        name="Labels",
        published=True,
        created_at=utcnow(),
        labels=(ProductionLabel(id="cat", name="Cat"), ProductionLabel(id="dog", name="Dog")),
    )


def _samples() -> tuple[PredictionSample, ...]:
    return tuple(
        PredictionSample(id=f"sample-{index}", filename=f"sample-{index}.png", width=100, height=80)
        for index in range(4)
    )


def test_coco_import_reports_each_bad_image_without_losing_valid_images() -> None:
    """Unknown categories, out-of-bounds boxes and empty images remain separate failures."""
    document = {
        "images": [
            {"id": index, "file_name": f"sample-{index}.png", "width": 100, "height": 80}
            for index in range(4)
        ],
        "categories": [{"id": 1, "name": "Cat"}, {"id": 2, "name": "Unknown"}],
        "annotations": [
            {"image_id": 0, "category_id": 1, "bbox": [10, 20, 30, 40], "score": 0.8},
            {"image_id": 1, "category_id": 2, "bbox": [10, 20, 30, 40]},
            {"image_id": 2, "category_id": 1, "bbox": [90, 20, 30, 40]},
            {"image_id": 99, "category_id": 1, "bbox": [0, 0, 1, 1]},
        ],
    }
    result = parse_coco(
        PredictionFile(filename="predictions.json", content=json.dumps(document)),
        _labels(),
        {},
        _samples(),
    )
    assert len(result.predictions) == 1
    assert result.predictions[0].annotation.sample_id == "sample-0"
    assert result.predictions[0].confidence == 0.8
    box = (
        result.predictions[0].annotation.boxes[0]
        if result.predictions[0].annotation.boxes
        else None
    )
    assert box is not None
    assert (box.category, box.x1, box.y1, box.x2, box.y2) == (
        "cat",
        10,
        20,
        40,
        60,
    )
    assert {item.filename for item in result.failures} == {
        "sample-1.png",
        "sample-2.png",
        "sample-3.png",
        "predictions.json",
    }


def test_coco_explicit_category_mapping_and_sample_identity_are_respected() -> None:
    """External numeric classes map to published identities and stable sample ids beat paths."""
    document = {
        "images": [
            {"id": "sample-0", "file_name": "nested/renamed.png", "width": 100, "height": 80}
        ],
        "annotations": [{"image_id": "sample-0", "category_id": 77, "bbox": [0, 0, 100, 80]}],
    }
    result = parse_coco(
        PredictionFile(filename="mapped.json", content=json.dumps(document)),
        _labels(),
        {"77": "dog"},
        _samples(),
    )
    assert not result.failures
    assert (
        result.predictions[0].annotation.boxes[0].category == "dog"
        if result.predictions[0].annotation.boxes
        else False
    )


@pytest.mark.parametrize("content", ["bad json", "[]", "{}", '{"images": [], "annotations": []}'])
def test_coco_malformed_or_empty_documents_report_file_error(content: str) -> None:
    """Malformed files are data failures, never exceptions that stop the outer import."""
    result = parse_coco(
        PredictionFile(filename="bad.json", content=content), _labels(), {}, _samples()
    )
    assert not result.predictions
    assert result.failures[0].filename == "bad.json"


@pytest.mark.parametrize(
    "image",
    [
        {"id": 1, "file_name": "missing.png", "width": 100, "height": 80},
        {"id": 1, "file_name": "sample-0.png", "width": 200, "height": 80},
        {"id": 1, "file_name": "sample-0.png", "width": 0, "height": 80},
    ],
)
def test_coco_rejects_missing_samples_and_false_image_dimensions(image: dict[str, object]) -> None:
    """Caller-supplied dimensions cannot enlarge the actual project's immutable image."""
    document = {
        "images": [image],
        "annotations": [{"image_id": 1, "category_id": 1, "bbox": [0, 0, 1, 1]}],
    }
    result = parse_coco(
        PredictionFile(filename="bad.json", content=json.dumps(document)),
        _labels(),
        {"1": "cat"},
        _samples(),
    )
    assert not result.predictions
    assert len(result.failures) == 1


def test_yolo_normalized_coordinates_round_trip_to_pixel_xyxy() -> None:
    """The conventional center/width/height form preserves COCO's corresponding pixel box."""
    result = parse_yolo(
        PredictionFile(filename="sample-0.txt", content="0 0.25 0.5 0.3 0.5 0.8\n"),
        _labels(),
        {},
        _samples(),
    )
    assert not result.failures
    annotation = result.predictions[0].annotation
    assert annotation.boxes is not None
    box = annotation.boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx((10, 20, 40, 60))
    assert result.predictions[0].confidence == 0.8


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("0 0.18999999999999997 0.5 0.38 0.2", (0, 40, 38, 60)),
        ("0 0.81 0.5 0.38 0.2", (62, 40, 100, 60)),
        ("0 0.5 0.18999999999999997 0.2 0.38", (40, 0, 60, 38)),
        ("0 0.5 0.81 0.2 0.38", (40, 62, 60, 100)),
    ],
    ids=("left", "right", "top", "bottom"),
)
def test_yolo_edge_roundoff_is_clipped_to_image_bounds(
    content: str, expected: tuple[float, float, float, float]
) -> None:
    """All four edges tolerate subpixel arithmetic noise and return bounded coordinates."""
    result = parse_yolo(
        PredictionFile(filename="edge.txt", content=content),
        _labels(),
        {},
        (PredictionSample(id="edge", filename="edge.png", width=100, height=100),),
    )
    assert not result.failures
    boxes = result.predictions[0].annotation.boxes
    assert boxes is not None
    box = boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx(expected)
    assert 0 <= box.x1 < box.x2 <= 100
    assert 0 <= box.y1 < box.y2 <= 100


@pytest.mark.parametrize(
    ("coordinates", "expected"),
    [
        ((-1e-14, 40, 38, 20), (0, 40, 38, 60)),
        ((62, 40, 38.000000000000014, 20), (62, 40, 100, 60)),
        ((40, -1e-14, 20, 38), (40, 0, 60, 38)),
        ((40, 62, 20, 38.000000000000014), (40, 62, 60, 100)),
    ],
    ids=("left", "right", "top", "bottom"),
)
def test_coco_edge_roundoff_is_clipped_to_image_bounds(
    coordinates: tuple[float, float, float, float], expected: tuple[float, float, float, float]
) -> None:
    """COCO xywh calculations share the same bounded edge handling as YOLO."""
    result = parse_coco(
        PredictionFile(
            filename="edge.json",
            content=json.dumps([{"image_id": "edge", "category_id": 1, "bbox": coordinates}]),
        ),
        _labels(),
        {"1": "cat"},
        (PredictionSample(id="edge", filename="edge.png", width=100, height=100),),
    )
    assert not result.failures
    boxes = result.predictions[0].annotation.boxes
    assert boxes is not None
    box = boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx(expected)
    assert 0 <= box.x1 < box.x2 <= 100
    assert 0 <= box.y1 < box.y2 <= 100


@pytest.mark.parametrize(
    "content",
    [
        "0 0.189999998 0.5 0.38 0.2",
        "0 0.810000002 0.5 0.38 0.2",
        "0 0.5 0.189999998 0.2 0.38",
        "0 0.5 0.810000002 0.2 0.38",
        "0 0.1799 0.5 0.38 0.2",
        "0 0.8201 0.5 0.38 0.2",
        "0 0.5 0.1799 0.2 0.38",
        "0 0.5 0.8201 0.2 0.38",
    ],
)
def test_yolo_boxes_beyond_pixel_tolerance_are_rejected(content: str) -> None:
    """Both 2e-7 pixel overflow and greater-than-one-pixel overflow remain invalid."""
    result = parse_yolo(
        PredictionFile(filename="edge.txt", content=content),
        _labels(),
        {},
        (PredictionSample(id="edge", filename="edge.png", width=100, height=100),),
    )
    assert not result.predictions
    assert len(result.failures) == 1


@pytest.mark.parametrize(
    "coordinates",
    [
        (-2e-7, 40, 38, 20),
        (62, 40, 38.0000002, 20),
        (40, -2e-7, 20, 38),
        (40, 62, 20, 38.0000002),
        (-1.01, 40, 38, 20),
        (62, 40, 39.01, 20),
        (40, -1.01, 20, 38),
        (40, 62, 20, 39.01),
        (-5e-8, 40, 1e-8, 20),
        (100.00000001, 40, 1e-8, 20),
        (40, -5e-8, 20, 1e-8),
        (40, 100.00000001, 20, 1e-8),
    ],
)
def test_coco_boxes_beyond_tolerance_or_without_clipped_area_are_rejected(
    coordinates: tuple[float, float, float, float],
) -> None:
    """Tolerance never admits actual overflow or a box wholly outside the image."""
    result = parse_coco(
        PredictionFile(
            filename="edge.json",
            content=json.dumps([{"image_id": "edge", "category_id": 1, "bbox": coordinates}]),
        ),
        _labels(),
        {"1": "cat"},
        (PredictionSample(id="edge", filename="edge.png", width=100, height=100),),
    )
    assert not result.predictions
    assert len(result.failures) == 1


@pytest.mark.parametrize(
    "content",
    [
        "",
        "\n",
        "0 0.5",
        "0 x 0.5 0.2 0.2",
        "99 0.5 0.5 0.2 0.2",
        "0 0.9 0.5 0.5 0.2",
        "0 0.5 0.5 -0.2 0.2",
        "0 0.5 0.5 nan 0.2",
        "0 0.5 0.5 0.2 0.2 1.5",
        "0 0.5 0.5 0.2 0.2 nan",
    ],
)
def test_yolo_reports_invalid_content_per_file(content: str) -> None:
    """Unmapped classes, empty files and malformed or unbounded boxes reject only this file."""
    result = parse_yolo(
        PredictionFile(filename="sample-0.txt", content=content), _labels(), {}, _samples()
    )
    assert not result.predictions
    assert result.failures[0].filename == "sample-0.txt"


def test_yolo_dimensions_and_identity_are_bound_to_the_project_sample() -> None:
    """Explicit identities support renamed label files while missing or fake sizes fail."""
    file = PredictionFile(filename="renamed.txt", sample_id="sample-0", content="0 0.5 0.5 1 1")
    assert len(parse_yolo(file, _labels(), {}, _samples()).predictions) == 1
    assert parse_yolo(
        file.model_copy(update={"image_width": 200}), _labels(), {}, _samples()
    ).failures
    assert parse_yolo(
        file.model_copy(update={"sample_id": None}), _labels(), {}, _samples()
    ).failures
    no_size = (PredictionSample(id="sample-0", filename="sample-0.png"),)
    assert parse_yolo(file, _labels(), {}, no_size).failures
    explicit = file.model_copy(update={"image_width": 100, "image_height": 80})
    assert len(parse_yolo(explicit, _labels(), {}, no_size).predictions) == 1


def test_coco_results_arrays_require_exact_sample_and_category_mappings() -> None:
    """Common detector result arrays import matched images and report unknown ones independently."""
    records = [
        {"image_id": "sample-0", "category_id": 42, "bbox": [0, 0, 10, 20], "score": 0.9},
        {"image_id": "unknown", "category_id": 42, "bbox": [0, 0, 10, 20]},
        "bad entry",
    ]
    file = PredictionFile(filename="results.json", content=json.dumps(records))
    result = parse_coco(file, _labels(), {"42": "cat"}, _samples())
    assert len(result.predictions) == 1
    assert result.predictions[0].annotation.sample_id == "sample-0"
    assert len(result.failures) == 2
    assert not parse_coco(file, _labels(), {}, _samples()).predictions
    single = PredictionFile(
        filename="results.json",
        sample_id="sample-0",
        content=json.dumps([{"image_id": 99, "category_id": 42, "bbox": [0, 0, 10, 20]}]),
    )
    assert len(parse_coco(single, _labels(), {"42": "cat"}, _samples()).predictions) == 1


def test_coco_multiple_result_images_cannot_reuse_one_explicit_sample_binding() -> None:
    """One file binding cannot silently relabel several unknown images as the same task."""
    records = [
        {"image_id": "sample-0", "category_id": 42, "bbox": [0, 0, 10, 20]},
        {"image_id": 100, "category_id": 42, "bbox": [0, 0, 10, 20]},
        {"image_id": 101, "category_id": 42, "bbox": [20, 20, 10, 20]},
    ]
    file = PredictionFile(
        filename="multiple-results.json", sample_id="sample-0", content=json.dumps(records)
    )
    result = parse_coco(file, _labels(), {"42": "cat"}, _samples())
    assert [prediction.annotation.sample_id for prediction in result.predictions] == ["sample-0"]
    assert {failure.filename for failure in result.failures} == {"100", "101"}
