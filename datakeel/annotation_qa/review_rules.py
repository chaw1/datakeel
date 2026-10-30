# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Draft and near-duplicate checks that still work when every sample has one annotator.

Label swap: a human object lies where an object of a confident model draft lies (same kind,
IoU >= 0.5 with labels ignored, the B1 geometry) but carries a different label.

Draft disagreement: after B1 matching under one label, and setting label swaps aside, the
share of draft and human objects left unmatched, weighted by the draft's confidence. Moving a
box by a few pixels keeps its IoU above 0.5, so it changes nothing.

Near-duplicate conflict: two near-duplicate images whose annotations do not agree under B1
once coordinates are scaled to each image's size. Both sides are flagged whoever submitted
first; when exactly one side agrees with its own confident draft, that side stays below the
high-risk line so the reviewer starts with the side more likely to be wrong.
"""

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from datakeel.annotation_qa.prelabel_match import (
    HIT_IOU,
    PrelabelObject,
    compare_records,
    object_iou,
    record_objects,
)
from datakeel.annotation_qa.review_messages import label_names, object_name, percent
from datakeel.annotation_qa.risk_scoring import disagreement_reason
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.prelabel_models import ObjectRef, RiskReason

CONFIDENT_DRAFT = 0.5
LABEL_SWAP_WEIGHT = 0.8
NEAR_DUPLICATE_WEIGHT = 0.6
NEAR_DUPLICATE_AGREEING_WEIGHT = 0.2


class Draft(NamedTuple):
    """The latest model revision of a task with per-object and overall confidence."""

    record: AnnotationRecord
    confidences: tuple[float, ...]
    confidence: float


class Neighbour(NamedTuple):
    """A submitted near-duplicate annotation, its draft agreement and a reviewer-facing name."""

    record: AnnotationRecord
    agrees: bool | None
    name: str


def _ref(item: PrelabelObject) -> ObjectRef:
    return ObjectRef.model_validate({"kind": item.kind, "index": item.position})


def label_swaps(draft: Draft, head: AnnotationRecord) -> tuple[tuple[int, int], ...]:
    """Pair confident draft objects with unmatched human objects at the same place, other label."""
    comparison = compare_records(draft.record, head)
    left, right = record_objects(draft.record), record_objects(head)
    free = set(range(len(right))) - {pair.human_index for pair in comparison.pairs}
    matched = {pair.model_index for pair in comparison.pairs}
    swaps: list[tuple[int, int]] = []
    for i, model in enumerate(left):
        if i in matched or draft.confidences[i] < CONFIDENT_DRAFT:
            continue
        scored = [
            (
                object_iou(
                    draft.record, model._replace(category=right[j].category), head, right[j]
                ),
                j,
            )
            for j in sorted(free)
            if right[j].kind == model.kind and right[j].category != model.category
        ]
        best = max(scored, default=(0.0, -1))
        if best[0] >= HIT_IOU:
            swaps.append((i, best[1]))
            free.discard(best[1])
    return tuple(swaps)


def _swap_reason(
    draft: Draft, head: AnnotationRecord, swap: tuple[int, int], names: Mapping[str, str]
) -> RiskReason:
    model, human = record_objects(draft.record)[swap[0]], record_objects(head)[swap[1]]
    confidence = draft.confidences[swap[0]]
    where, where_zh = object_name(human.kind, human.position)
    chosen, chosen_zh = label_names(human.category.split("\x1f"), names)
    drafted, drafted_zh = label_names(model.category.split("\x1f"), names)
    sure = percent(confidence)
    if human.kind == "label_set":
        message = (
            f"The chosen labels {chosen} differ from the model draft's {drafted} ({sure} sure)"
        )
        message_zh = f"所选标签{chosen_zh}和模型草稿以 {sure} 把握给出的{drafted_zh}不同"
    else:
        message = f"{where} is labelled {chosen}, but the model draft put {drafted} in the same "
        message += f"place with {sure} confidence"
        message_zh = (
            f"{where_zh}标成了{chosen_zh}，模型草稿在同一位置以 {sure} 的把握标的是{drafted_zh}"  # noqa: RUF001  # Chinese punctuation is intended.
        )
    return RiskReason(
        code="label_swap",
        weight=round(LABEL_SWAP_WEIGHT * confidence, 6),
        message=message,
        message_zh=message_zh,
        objects=(_ref(human),),
    )


def _disagreement_reason(
    draft: Draft, head: AnnotationRecord, swaps: Sequence[tuple[int, int]]
) -> RiskReason | None:
    comparison = compare_records(draft.record, head)
    left, right = record_objects(draft.record), record_objects(head)
    missing = set(range(len(left))) - {pair.model_index for pair in comparison.pairs}
    missing -= {i for i, _ in swaps}
    extra = set(range(len(right))) - {pair.human_index for pair in comparison.pairs}
    extra -= {j for _, j in swaps}
    if not missing and not extra:
        return None
    confidence = max((draft.confidences[i] for i in missing), default=draft.confidence)
    difference = (len(missing) + len(extra)) / (len(left) + len(right))
    reason = disagreement_reason(
        confidence, difference, tuple(_ref(right[j]) for j in sorted(extra))
    )
    if reason is None:
        return None
    sure = percent(confidence)
    return reason.model_copy(
        update={
            "message": f"{len(missing)} object(s) of a {sure} confident model draft have no "
            f"matching annotation, and {len(extra)} annotated object(s) are not in the draft",
            "message_zh": f"模型草稿（把握 {sure}）里有 {len(missing)} 个对象没有对应的标注，"  # noqa: RUF001  # Chinese punctuation is intended.
            f"另有 {len(extra)} 个标注在草稿里找不到",
        }
    )


def draft_reasons(
    draft: Draft, head: AnnotationRecord, names: Mapping[str, str]
) -> list[RiskReason]:
    """Flag label swaps against a confident draft and B1-unmatched objects."""
    swaps = label_swaps(draft, head)
    reasons = [_swap_reason(draft, head, swap, names) for swap in swaps]
    disagreement = _disagreement_reason(draft, head, swaps)
    return [*reasons, disagreement] if disagreement is not None else reasons


def agrees_with_draft(draft: Draft | None, head: AnnotationRecord) -> bool | None:
    """Return whether every object matches a confident draft under B1, or None without one."""
    if draft is None or min(draft.confidences, default=draft.confidence) < CONFIDENT_DRAFT:
        return None
    return compare_records(draft.record, head).all_hit()


def _scaled(record: AnnotationRecord) -> AnnotationRecord:
    width, height = record.image_width, record.image_height
    if not width or not height:
        return record
    boxes = tuple(
        box.model_copy(
            update={"x1": box.x1 / width, "x2": box.x2 / width, "y1": box.y1 / height}
            | {"y2": box.y2 / height}
        )
        for box in record.boxes or ()
    )
    polygons = tuple(
        polygon.model_copy(
            update={
                "points": tuple(
                    point.model_copy(update={"x": point.x / width, "y": point.y / height})
                    for point in polygon.points
                )
            }
        )
        for polygon in record.polygons or ()
    )
    return record.model_copy(
        update={
            "boxes": boxes if record.boxes is not None else None,
            "polygons": polygons if record.polygons is not None else None,
        }
    )


def near_duplicate_reason(
    head: AnnotationRecord,
    neighbours: Sequence[Neighbour],
    *,
    agrees: bool | None,
) -> RiskReason | None:
    """Flag a head whose annotation differs from any near-duplicate image's annotation."""
    scaled = _scaled(head)
    compared = [(item, compare_records(_scaled(item.record), scaled)) for item in neighbours]
    conflicts = [(item, comparison) for item, comparison in compared if not comparison.all_hit()]
    if not conflicts:
        return None
    other, comparison = conflicts[0]
    likely_other = agrees is True and all(item.agrees is False for item, _ in conflicts)
    matched = {pair.human_index for pair in comparison.pairs}
    objects = tuple(
        _ref(item) for position, item in enumerate(record_objects(head)) if position not in matched
    )
    suffix, suffix_zh = (
        (
            "; this one matches its model draft, so the other is more likely wrong",
            "，这张与模型草稿一致，另一张更可能有错",  # noqa: RUF001  # Chinese punctuation is intended.
        )
        if likely_other
        else ("", "")
    )
    return RiskReason(
        code="near_duplicate_conflict",
        weight=NEAR_DUPLICATE_AGREEING_WEIGHT if likely_other else NEAR_DUPLICATE_WEIGHT,
        message=f'This image nearly duplicates "{other.name}", but the two are annotated '
        f"differently{suffix}",
        message_zh=f"这张图和「{other.name}」几乎一样，但两张的标注不一致{suffix_zh}",  # noqa: RUF001  # Chinese punctuation is intended.
        objects=objects,
    )
