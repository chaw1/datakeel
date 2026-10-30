# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Draft and near-duplicate review rules for projects with one annotator per sample."""

from datakeel.annotation_qa import (
    HIGH_RISK,
    Draft,
    Neighbour,
    draft_reasons,
    near_duplicate_reason,
    risk_score,
)
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord

NAMES = {"cat": "Cat", "dog": "Dog"}


def _record(
    boxes: list[tuple[str, float, float, float, float]],
    *,
    labels: tuple[str, ...] | None = None,
    size: tuple[int, int] = (160, 120),
) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id="sample",
        annotator_id="local",
        labels=labels,
        boxes=tuple(
            AnnotationBox(category=box[0], x1=box[1], y1=box[2], x2=box[3], y2=box[4])
            for box in boxes
        ),
        image_width=size[0],
        image_height=size[1],
    )


def _draft(record: AnnotationRecord, confidence: float) -> Draft:
    count = len(record.boxes or ()) + (1 if record.labels else 0)
    return Draft(record, (confidence,) * count, confidence)


def test_moving_a_box_a_few_pixels_is_not_a_disagreement() -> None:
    """B1 matching at IoU 0.5: a 3-pixel nudge of a 95% draft box adds no risk at all."""
    draft = _draft(_record([("cat", 20, 20, 80, 70)]), 0.95)
    nudged = _record([("cat", 23, 18, 83, 72)])
    assert draft_reasons(draft, nudged, NAMES) == []


def test_relabelling_a_confident_draft_box_is_a_high_risk_swap() -> None:
    """Same place, different label: the swap is located and weighted by draft confidence."""
    draft = _draft(_record([("cat", 20, 20, 80, 70), ("dog", 90, 20, 150, 70)]), 0.95)
    swapped = _record([("cat", 21, 20, 80, 71), ("cat", 90, 21, 151, 70)])
    reasons = draft_reasons(draft, swapped, NAMES)
    assert [reason.code for reason in reasons] == ["label_swap"]
    assert reasons[0].weight == 0.76
    assert [(item.kind, item.index) for item in reasons[0].objects] == [("box", 1)]
    assert reasons[0].message.startswith('Box 2 is labelled "Cat"')
    assert '"Dog"' in reasons[0].message
    assert "第 2 个框标成了「Cat」" in reasons[0].message_zh
    assert risk_score(reasons) >= HIGH_RISK


def test_unsure_draft_does_not_turn_a_relabel_into_a_swap() -> None:
    """Below 50% draft confidence a different label is only a weak disagreement."""
    draft = _draft(_record([("dog", 20, 20, 80, 70)]), 0.4)
    reasons = draft_reasons(draft, _record([("cat", 20, 20, 80, 70)]), NAMES)
    assert [reason.code for reason in reasons] == ["prelabel_disagreement"]
    assert risk_score(reasons) < HIGH_RISK


def test_removing_a_confident_draft_box_is_a_disagreement() -> None:
    """A dropped draft box and a box drawn elsewhere are counted and located."""
    draft = _draft(_record([("cat", 20, 20, 80, 70)]), 0.9)
    reasons = draft_reasons(draft, _record([("cat", 100, 60, 150, 110)]), NAMES)
    assert [reason.code for reason in reasons] == ["prelabel_disagreement"]
    assert reasons[0].weight == 0.45
    assert [(item.kind, item.index) for item in reasons[0].objects] == [("box", 0)]
    assert "1 object(s)" in reasons[0].message
    assert "1 个对象没有对应的标注" in reasons[0].message_zh


def test_label_set_swap_names_both_label_sets() -> None:
    """For classification the whole label set is the object; wording names both sets."""
    draft = _draft(_record([], labels=("cat",)), 0.9)
    reasons = draft_reasons(draft, _record([], labels=("cat", "dog")), NAMES)
    assert [reason.code for reason in reasons] == ["label_swap"]
    assert reasons[0].message == (
        'The chosen labels "Cat", "Dog" differ from the model draft\'s "Cat" (90% sure)'
    )
    assert reasons[0].objects[0].kind == "label_set"


def test_near_duplicates_compare_boxes_relative_to_image_size() -> None:
    """A half-size copy with the same relative box is consistent; a missing box is not."""
    head = _record([("cat", 20, 20, 80, 70)])
    resized = _record([("cat", 10, 10, 40, 35)], size=(80, 60))
    assert near_duplicate_reason(head, [Neighbour(resized, None, "a.png")], agrees=None) is None
    empty = _record([], size=(80, 60))
    reason = near_duplicate_reason(head, [Neighbour(empty, None, "a.png")], agrees=None)
    assert reason is not None
    assert reason.weight >= HIGH_RISK
    assert '"a.png"' in reason.message
    assert "「a.png」" in reason.message_zh
    assert [(item.kind, item.index) for item in reason.objects] == [("box", 0)]


def test_near_duplicate_side_that_matches_its_draft_stays_below_high_risk() -> None:
    """Both sides are flagged; the side agreeing with its draft is ranked after the other."""
    head = _record([("cat", 20, 20, 80, 70)])
    other = _record([("dog", 20, 20, 80, 70)])
    right = near_duplicate_reason(head, [Neighbour(other, agrees=False, name="b.png")], agrees=True)
    wrong = near_duplicate_reason(other, [Neighbour(head, agrees=True, name="a.png")], agrees=False)
    assert right is not None
    assert wrong is not None
    assert right.weight < HIGH_RISK <= wrong.weight
    assert "more likely wrong" in right.message
