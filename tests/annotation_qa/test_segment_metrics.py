# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unsupported segment metrics degrade explicitly instead of reporting false agreement."""

from datakeel.annotation_qa import evaluate_annotations
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationRecord,
    AnnotationSegment,
)
from datakeel.storage.workbench_risk import draft_difference, prelabel_difference


def _record(segments: tuple[AnnotationSegment, ...] | None) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id="audio",
        annotator_id="ann",
        labels=(),
        segments=segments,
        media_duration_ms=1000 if segments is not None else None,
    )


def test_segment_agreement_is_explicitly_unsupported_for_empty_and_nonempty() -> None:
    """Reviewed empty and populated batches both expose a null unsupported metric."""
    for segments in ((), (AnnotationSegment(category="a", start_ms=0, end_ms=1),)):
        result = evaluate_annotations(AnnotationBatch(annotations=(_record(segments),)))
        assert result.segment_agreement is not None
        assert result.segment_agreement.value is None
        assert "not supported" in (result.segment_agreement.reason or "")


def test_mixed_classification_cannot_hide_segments_behind_perfect_agreement() -> None:
    """Exact and draft comparisons include segments and refuse unsupported automatic scores."""
    left = _record((AnnotationSegment(category="a", start_ms=0, end_ms=1000),))
    right = _record((AnnotationSegment(category="a", start_ms=0, end_ms=500),))
    assert prelabel_difference(left, right) > 0
    assert draft_difference(left, left) is None


def test_legacy_records_do_not_gain_an_unsupported_metric() -> None:
    """The five existing components keep their prior metric shape."""
    result = evaluate_annotations(AnnotationBatch(annotations=(_record(None),)))
    assert result.segment_agreement is None
