# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Panel consensus findings for boxes and spans."""

from datakeel.annotation_qa.consensus import consensus_findings, span_jaccard
from datakeel.annotation_qa.service import evaluate_annotations
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
)


def _box(x: float, category: str = "car", size: float = 10) -> AnnotationBox:
    return AnnotationBox(category=category, x1=x, y1=0, x2=x + size, y2=size)


def _span(start: int, end: int, category: str = "PER") -> AnnotationSpan:
    return AnnotationSpan(category=category, start=start, end=end)


def _panel(**records: tuple[AnnotationBox, ...] | None) -> AnnotationBatch:
    return AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(sample_id="s", annotator_id=name, boxes=boxes)
            for name, boxes in records.items()
        )
    )


def _spans(**records: tuple[AnnotationSpan, ...] | None) -> AnnotationBatch:
    return AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(sample_id="s", annotator_id=name, spans=spans, text_length=50)
            for name, spans in records.items()
        )
    )


def _codes(batch: AnnotationBatch) -> list[tuple[str, str]]:
    return sorted((item.annotator_id, item.code) for item in consensus_findings(batch))


def test_box_category_minority_missing_and_extra_against_panel_majority() -> None:
    """Majority boxes define consensus; the third annotator's deviations are each reported."""
    batch = _panel(
        a=(_box(0), _box(50)),
        b=(_box(1), _box(51)),
        c=(_box(0, "truck"), _box(200)),
    )
    assert _codes(batch) == [
        ("c", "bbox_category_minority"),
        ("c", "bbox_extra"),
        ("c", "bbox_missing"),
    ]
    missing = next(item for item in consensus_findings(batch) if item.code == "bbox_missing")
    assert missing.evidence[0] == "support=2/3"


def test_agreeing_panel_and_small_panels_produce_no_consensus_findings() -> None:
    """Jittered agreement is consensus; two annotators cannot form a minority."""
    assert _codes(_panel(a=(_box(0),), b=(_box(1),), c=(_box(0.5),))) == []
    assert _codes(_panel(a=(_box(0),), b=(_box(0, "truck"),))) == []
    assert _codes(_panel(a=(_box(0),), b=(_box(0),), c=None)) == []


def test_reviewed_empty_record_is_missing_but_absent_record_is_not() -> None:
    """An empty tuple is a reviewed record without boxes; None is not reviewed."""
    assert _codes(_panel(a=(_box(0),), b=(_box(0),), c=())) == [("c", "bbox_missing")]


def test_invalid_item_of_consensus_category_is_not_also_missing() -> None:
    """The bounds rule already reports an invalid box; consensus does not double count it."""
    reversed_box = AnnotationBox(category="car", x1=10, y1=0, x2=0, y2=10)
    assert _codes(_panel(a=(_box(0),), b=(_box(0),), c=(reversed_box,))) == []


def test_span_boundary_category_missing_and_extra() -> None:
    """Spans cluster on positive overlap; offsets and categories are voted separately."""
    batch = _spans(
        a=(_span(0, 5), _span(10, 15, "ORG")),
        b=(_span(0, 5), _span(10, 15, "ORG")),
        c=(_span(0, 7), _span(10, 15, "LOC"), _span(30, 35)),
        d=(_span(0, 5), _span(10, 15, "ORG")),
    )
    assert _codes(batch) == [
        ("c", "span_boundary_minority"),
        ("c", "span_category_minority"),
        ("c", "span_extra"),
    ]
    assert _codes(_spans(a=(_span(0, 5),), b=(_span(0, 5),), c=())) == [("c", "span_missing")]


def test_span_jaccard_definition() -> None:
    """Half-open interval intersection over union; touching intervals do not overlap."""
    assert span_jaccard((0, 5), (0, 7)) == 5 / 7
    assert span_jaccard((0, 5), (5, 9)) == 0


def test_chained_same_annotator_boxes_report_one_duplicate_without_false_missing() -> None:
    """Two sub-threshold self duplicates joined through peers flag only their author."""
    left = AnnotationBox(category="can", x1=0, y1=0, x2=18, y2=22)
    right = left.model_copy(update={"x1": 1, "x2": 19})
    batch = _panel(a=(left, right), b=(left,), c=(right,))
    findings = evaluate_annotations(batch).findings
    assert [(item.annotator_id, item.code) for item in findings] == [("a", "duplicate_bbox")]
    repaired = _panel(a=(left,), b=(left,), c=(right,))
    assert evaluate_annotations(repaired).findings == ()
    assert _codes(_panel(a=(left, right), b=(left,), c=(right,), d=())) == [
        ("a", "duplicate_bbox"),
        ("d", "bbox_missing"),
    ]


def test_cluster_votes_count_people_instead_of_repeated_category_entries() -> None:
    """Repeated votes cannot suppress a two-person majority or turn peers into minorities."""
    batch = _panel(a=(_box(0, "truck"), _box(1, "truck")), b=(_box(0),), c=(_box(1),))
    findings = consensus_findings(batch)
    minority = [item for item in findings if item.code == "bbox_category_minority"]
    assert [item.annotator_id for item in minority] == ["a", "a"]
    assert all(item.evidence[0] == "majority=car; votes=2/3" for item in minority)
    assert _codes(batch).count(("a", "duplicate_bbox")) == 1


def test_conflicting_values_from_one_annotator_abstain_in_cluster_vote() -> None:
    """One person's inconsistent entries cannot supply two votes for different categories."""
    batch = _panel(a=(_box(0, "truck"), _box(1)), b=(_box(0),), c=(_box(1, "truck"),))
    assert _codes(batch) == [("a", "duplicate_bbox")]


def test_span_chain_reports_duplicate_without_inventing_boundary_majority() -> None:
    """Different offsets from one author abstain, leaving a three-person boundary tie."""
    batch = _spans(a=(_span(0, 5), _span(1, 6)), b=(_span(0, 5),), c=(_span(1, 6),))
    assert _codes(batch) == [("a", "duplicate_span")]


def test_cluster_duplicates_share_self_duplicate_identity_and_count_extra_entries() -> None:
    """Three chained entries create two findings across structural and consensus checks."""
    boxes = _panel(a=(_box(0), _box(0.4), _box(0.8)), b=(_box(0),), c=(_box(0.4),), d=(_box(0.8),))
    spans = _spans(
        a=(_span(0, 5), _span(1, 6), _span(2, 7)),
        b=(_span(0, 5),),
        c=(_span(1, 6),),
        d=(_span(2, 7),),
    )
    for batch, code in (
        (boxes, "duplicate_bbox"),
        (spans, "duplicate_span"),
        (_panel(a=(_box(0),) * 3), "duplicate_bbox"),
        (_spans(a=(_span(0, 5),) * 3), "duplicate_span"),
    ):
        observed = [(item.annotator_id, item.code) for item in evaluate_annotations(batch).findings]
        assert observed == [
            ("a", code),
            ("a", code),
        ]
