# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rework counts must not change when an unrelated item edit renumbers a record."""

from datakeel.annotation_qa.rework import compare_rework
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
)

_ENTITIES = (("PARTY", 300, 330), ("DATE", 400, 412), ("AMOUNT", 500, 512), ("TERM", 600, 615))


def _spans(*entities: tuple[str, int, int]) -> tuple[AnnotationSpan, ...]:
    return tuple(AnnotationSpan(category=c, start=a, end=b) for c, a, b in entities)


def _span_batch(second: tuple[AnnotationSpan, ...]) -> AnnotationBatch:
    return AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(
                sample_id="contract-1",
                annotator_id=annotator,
                spans=second if annotator == "lex-2" else _spans(*_ENTITIES),
                text_length=2000,
            )
            for annotator in ("lex-1", "lex-2", "lex-3")
        )
    )


def _counts(before: AnnotationBatch, after: AnnotationBatch) -> tuple[int, int, int, int]:
    result = compare_rework(before, after)
    return (
        result.corrected_count,
        result.introduced_count,
        result.remaining_count,
        result.unassessed_count,
    )


def test_deleting_an_earlier_extra_span_keeps_a_later_boundary_error_remaining() -> None:
    """Removing the extra span at index 0 renumbers the unfixed boundary error from 3 to 2."""
    drifted = list(_spans(*_ENTITIES))
    drifted[2] = AnnotationSpan(category="AMOUNT", start=500, end=518)
    extra = AnnotationSpan(category="PARTY", start=40, end=70)
    before = _span_batch((extra, *drifted))
    after = _span_batch(tuple(drifted))
    result = compare_rework(before, after)
    assert [item.code for item in result.corrected] == ["span_extra"]
    assert [item.code for item in result.remaining] == ["span_boundary_minority"]
    assert _counts(before, after) == (1, 0, 1, 0)


def test_renumbered_findings_pair_only_within_the_same_rule_and_record() -> None:
    """A fix plus a different new error on the same record stays corrected plus introduced."""
    drifted = list(_spans(*_ENTITIES))
    drifted[2] = AnnotationSpan(category="AMOUNT", start=500, end=518)
    drifted[3] = AnnotationSpan(category="TERM", start=600, end=621)
    extra = AnnotationSpan(category="PARTY", start=40, end=70)
    before = _span_batch((extra, *drifted))
    repaired = list(drifted)
    repaired[2] = AnnotationSpan(category="AMOUNT", start=500, end=512)
    missing_date = (repaired[0], repaired[2], repaired[3])
    after = _span_batch(missing_date)
    result = compare_rework(before, after)
    assert sorted(item.code for item in result.corrected) == [
        "span_boundary_minority",
        "span_extra",
    ]
    assert [item.code for item in result.remaining] == ["span_boundary_minority"]
    assert [item.code for item in result.introduced] == ["span_missing"]


def _boxes(*items: tuple[str, float]) -> tuple[AnnotationBox, ...]:
    return tuple(
        AnnotationBox(category=category, x1=x, y1=100, x2=x + 60, y2=190) for category, x in items
    )


def test_deleting_an_earlier_extra_box_keeps_a_later_category_error_remaining() -> None:
    """Box findings keyed by position survive renumbering of the same annotator's record."""
    shelf = (("can", 100.0), ("bottle", 300.0), ("can", 500.0))
    wrong = (("can", 100.0), ("bottle", 300.0), ("bottle", 500.0))

    def batch(third: tuple[AnnotationBox, ...]) -> AnnotationBatch:
        return AnnotationBatch(
            annotations=tuple(
                AnnotationRecord(
                    sample_id="shelf-1",
                    annotator_id=annotator,
                    boxes=third if annotator == "qa-3" else _boxes(*shelf),
                    image_width=1920,
                    image_height=1080,
                )
                for annotator in ("qa-1", "qa-2", "qa-3")
            )
        )

    before = batch(_boxes(("carton", 900.0), *wrong))
    after = batch(_boxes(*wrong))
    result = compare_rework(before, after)
    assert [item.code for item in result.corrected] == ["bbox_extra"]
    assert [item.code for item in result.remaining] == ["bbox_category_minority"]
    assert _counts(before, after) == (1, 0, 1, 0)
