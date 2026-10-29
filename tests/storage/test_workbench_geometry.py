# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Polygon templates preserve attributes and enforce finite source-image geometry."""

from pathlib import Path

import pytest
from pydantic import ValidationError as SchemaValidationError

from datakeel.core.annotation_models import AnnotationPoint, AnnotationPolygon
from datakeel.core.errors import ValidationError
from datakeel.storage.database import Database
from datakeel.storage.production_catalog import normalize_annotation, validate_annotation
from tests.workbench_helpers import annotation_for, seed_workbench


def test_polygon_template_normalizes_stable_labels_and_preserves_shape_properties(
    db: Database, tmp_path: Path
) -> None:
    """Polygons use published label ids while shape and record attributes survive unchanged."""
    project, tasks = seed_workbench(db, tmp_path / "polygon", "polygon")
    original = annotation_for("polygon", tasks[0].sample_id)
    with db.session() as session:
        normalized = normalize_annotation(session, project, original)
        validate_annotation(session, project, normalized)
    assert normalized.polygons is not None
    assert normalized.polygons[0].category == "cat"
    assert normalized.polygons[0].attributes == {"part": "tail"}
    assert normalized.attributes == original.attributes
    assert original.polygons is not None
    assert normalized.polygons[0].points == original.polygons[0].points


def test_polygon_rejects_outside_image_duplicate_vertices_and_zero_area(
    db: Database, tmp_path: Path
) -> None:
    """Invalid polygons cannot be persisted as a production revision even with valid labels."""
    project, tasks = seed_workbench(db, tmp_path / "invalid", "polygon")
    original = annotation_for("polygon", tasks[0].sample_id)
    assert original.polygons is not None
    polygon = original.polygons[0]
    invalid_points = (
        ((-1, 0), (20, 0), (20, 20)),
        ((0, 0), (101, 0), (20, 20)),
        ((0, 0), (20, 81), (20, 20)),
        ((1, 1), (1, 1), (2, 2)),
        ((0, 0), (1, 1), (2, 2)),
    )
    for points in invalid_points:
        invalid = polygon.model_copy(
            update={"points": tuple(AnnotationPoint(x=x, y=y) for x, y in points)}
        )
        annotation = original.model_copy(update={"polygons": (invalid,)})
        with db.session() as session, pytest.raises(ValidationError):
            validate_annotation(session, project, annotation)
    with pytest.raises(SchemaValidationError):
        AnnotationPoint(x=float("inf"), y=0)
    with pytest.raises(SchemaValidationError):
        AnnotationPolygon(category="cat", points=(AnnotationPoint(x=0, y=0),))
