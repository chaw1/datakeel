# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Match model and human objects one-to-one under one label, ordered by descending IoU.

Objects are the classification label set (one object when nonempty), then boxes, polygons
and spans in record order; model revisions store per-object confidence in this same order.
Pairs are sorted by IoU from high to low with model then human index as tie breaks and taken
greedily. Because every pair at or above 0.75 is considered before any lower pair, counting
matched pairs with IoU >= 0.75 equals rerunning the greedy match restricted to that threshold.
"""

from typing import NamedTuple

from pydantic import JsonValue

from datakeel.annotation_qa.geometry import box_iou
from datakeel.annotation_qa.polygon_area import polygon_iou
from datakeel.core.annotation_models import AnnotationRecord

HIT_IOU = 0.5
STRICT_IOU = 0.75


class PrelabelObject(NamedTuple):
    """One comparable object with its kind, record-order position and label key."""

    kind: str
    position: int
    category: str
    attributes: dict[str, JsonValue]


class ObjectPair(NamedTuple):
    """A greedy one-to-one match at or above the hit threshold."""

    model_index: int
    human_index: int
    iou: float
    attributes_equal: bool


class RecordComparison(NamedTuple):
    """Per-object hits for one model draft against its human reference."""

    model_count: int
    human_count: int
    pairs: tuple[ObjectPair, ...]

    def hits(self, threshold: float = HIT_IOU) -> int:
        """Count matched pairs at or above the threshold."""
        return sum(pair.iou >= threshold for pair in self.pairs)

    def all_hit(self, threshold: float = HIT_IOU) -> bool:
        """Require every model and every human object to be matched at the threshold."""
        hits = self.hits(threshold)
        return hits == self.model_count == self.human_count

    def model_hits(self, threshold: float = HIT_IOU) -> tuple[bool, ...]:
        """Return one hit flag per model object in canonical object order."""
        matched = {pair.model_index for pair in self.pairs if pair.iou >= threshold}
        return tuple(index in matched for index in range(self.model_count))


def record_objects(record: AnnotationRecord) -> tuple[PrelabelObject, ...]:
    """List comparable objects in the canonical order used for stored confidences."""
    objects: list[PrelabelObject] = []
    if record.labels:
        key = "\x1f".join(sorted(set(record.labels)))
        objects.append(PrelabelObject("label_set", 0, key, dict(record.attributes)))
    objects.extend(
        PrelabelObject("box", index, box.category, dict(box.attributes))
        for index, box in enumerate(record.boxes or ())
    )
    objects.extend(
        PrelabelObject("polygon", index, polygon.category, dict(polygon.attributes))
        for index, polygon in enumerate(record.polygons or ())
    )
    objects.extend(
        PrelabelObject("span", index, span.category, dict(span.attributes))
        for index, span in enumerate(record.spans or ())
    )
    return tuple(objects)


def span_iou(left: tuple[int, int], right: tuple[int, int]) -> float:
    """Compute half-open character interval IoU; empty or reversed spans never match."""
    if left[1] <= left[0] or right[1] <= right[0]:
        return 0.0
    intersection = max(0, min(left[1], right[1]) - max(left[0], right[0]))
    union = (left[1] - left[0]) + (right[1] - right[0]) - intersection
    return intersection / union


def object_iou(
    model: AnnotationRecord,
    left: PrelabelObject,
    human: AnnotationRecord,
    right: PrelabelObject,
) -> float:
    """Score two same-kind objects; label sets agree only when they are identical."""
    if left.kind != right.kind or left.category != right.category:
        return 0.0
    if left.kind == "label_set":
        return 1.0
    if left.kind == "box":
        return box_iou((model.boxes or ())[left.position], (human.boxes or ())[right.position])
    if left.kind == "polygon":
        first = (model.polygons or ())[left.position].points
        second = (human.polygons or ())[right.position].points
        return polygon_iou(
            tuple((point.x, point.y) for point in first),
            tuple((point.x, point.y) for point in second),
        )
    first_span = (model.spans or ())[left.position]
    second_span = (human.spans or ())[right.position]
    return span_iou((first_span.start, first_span.end), (second_span.start, second_span.end))


def compare_records(model: AnnotationRecord, human: AnnotationRecord) -> RecordComparison:
    """Greedily match same-label objects by descending IoU, keeping pairs at IoU >= 0.5."""
    left, right = record_objects(model), record_objects(human)
    candidates = sorted(
        (
            (score, i, j)
            for i, first in enumerate(left)
            for j, second in enumerate(right)
            if (score := object_iou(model, first, human, second)) >= HIT_IOU
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    used_left: set[int] = set()
    used_right: set[int] = set()
    pairs: list[ObjectPair] = []
    for score, i, j in candidates:
        if i in used_left or j in used_right:
            continue
        used_left.add(i)
        used_right.add(j)
        pairs.append(ObjectPair(i, j, score, left[i].attributes == right[j].attributes))
    return RecordComparison(len(left), len(right), tuple(sorted(pairs)))
