# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit COCO labels retain their source and convert xywh to original-image xyxy."""

import json
from pathlib import Path

import pytest

from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import EvidenceValue, ImageRegion, Whole
from datakeel.core.models import FileItem
from tests.operators.evidence.helpers import drafts, run_node


def _replace_annotation(sample: FileItem, document: str) -> None:
    sidecar = sample_sidecars(sample).annotation
    assert sidecar is not None
    Path(sidecar.path).write_text(document, encoding="utf-8")


def test_annotation_when_present_retains_xyxy_and_both_sources(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify bbox conversion and anchors for both pixels and annotation bytes."""
    image = run_node("image_phash", sample, tmp_path)
    result = run_node("annotation_labels", image, tmp_path)
    person = next(
        draft
        for draft in drafts(result)
        if draft.object == EvidenceValue(concept="person", value="present")
    )
    region = person.anchors[0].selector
    assert isinstance(region, ImageRegion)
    assert region.bbox == (24, 28, 72, 100)
    assert (region.width, region.height) == (192, 128)
    assert isinstance(person.anchors[-1].selector, Whole)
    assert person.anchors[0].asset_ref.asset_id == sample.id
    assert person.anchors[-1].asset_ref.asset_id == sample_sidecars(sample).annotation.id
    assert result.metadata["annotation_available"]


def test_annotation_when_alias_supplied_normalizes_and_reads_image_dimensions(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify COCO subset documents need not duplicate image dimensions."""
    _replace_annotation(
        sample,
        json.dumps(
            {
                "annotations": [
                    {"category": "PEDESTRIAN", "bbox": [1, 2, 3, 4], "id": 1},
                    {"category": "unmapped", "bbox": [0, 0, 5, 5]},
                ]
            }
        ),
    )
    result = run_node("annotation_labels", sample, tmp_path)
    assert result.metadata["annotation_categories"] == ["person"]
    assert result.metadata["annotation_boxes"][0]["bbox"] == [1, 2, 4, 6]


@pytest.mark.parametrize(
    "document", ["not-json", '{"annotations":[{"category":"person","bbox":[-1,0,5,5]}]}']
)
def test_annotation_when_invalid_returns_unknown_and_failure(
    sample: FileItem, tmp_path: Path, document: str
) -> None:
    """Verify malformed annotation inputs never become observed absence."""
    _replace_annotation(sample, document)
    result = run_node("annotation_labels", sample, tmp_path)
    assert result.metadata["evidence_failed"]
    assert not result.metadata["annotation_available"]
    assert all(
        isinstance(draft.object, EvidenceValue) and draft.object.value == "unknown"
        for draft in drafts(result)
    )


def test_annotation_when_missing_keeps_unknown_without_failure(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify an absent annotation sidecar differs from a malformed supplied one."""
    sidecars = sample_sidecars(sample).model_copy(update={"annotation": None})
    altered = sample.model_copy(
        update={"metadata": {**sample.metadata, "evidence_sample": sidecars.model_dump()}}
    )
    result = run_node("annotation_labels", altered, tmp_path)
    assert not result.metadata["annotation_available"]
    assert not result.metadata["evidence_failed"]
