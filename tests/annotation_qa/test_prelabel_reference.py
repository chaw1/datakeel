# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Box P/R/F1 at IoU 0.5 and 0.75 agree value by value with an independent numpy reference.

The reference builds a full IoU matrix per label, repeatedly takes the global maximum (ties by
model then human index), and matches each threshold separately, as COCO does per IoU level.
"""

import random

import numpy as np
import pytest

from datakeel.annotation_qa import prelabel_accuracy
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord

LABELS = ("cat", "dog", "car")


def _iou_matrix(model: list[AnnotationBox], human: list[AnnotationBox]) -> np.ndarray:
    a = np.array([[box.x1, box.y1, box.x2, box.y2] for box in model], dtype=float).reshape(-1, 4)
    b = np.array([[box.x1, box.y1, box.x2, box.y2] for box in human], dtype=float).reshape(-1, 4)
    left = np.maximum(a[:, None, 0], b[None, :, 0])
    top = np.maximum(a[:, None, 1], b[None, :, 1])
    right = np.minimum(a[:, None, 2], b[None, :, 2])
    bottom = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(right - left, 0, None) * np.clip(bottom - top, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    union = area_a[:, None] + area_b[None, :] - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)


def _reference_hits(
    model: list[AnnotationBox], human: list[AnnotationBox], threshold: float
) -> int:
    hits = 0
    for label in LABELS:
        mine = [box for box in model if box.category == label]
        theirs = [box for box in human if box.category == label]
        if not mine or not theirs:
            continue
        matrix = _iou_matrix(mine, theirs)
        while matrix.size and matrix.max() >= threshold:
            best = matrix.max()
            rows, cols = np.nonzero(matrix == best)
            row, col = min(zip(rows.tolist(), cols.tolist(), strict=True))
            hits += 1
            matrix[row, :] = -1
            matrix[:, col] = -1
    return hits


def _scene(rng: random.Random, count: int) -> list[AnnotationBox]:
    boxes: list[AnnotationBox] = []
    for _ in range(count):
        x, y = rng.uniform(6, 80), rng.uniform(6, 80)  # Valid after a 6-pixel jitter.
        w, h = rng.uniform(5, 30), rng.uniform(5, 30)
        boxes.append(AnnotationBox(category=rng.choice(LABELS), x1=x, y1=y, x2=x + w, y2=y + h))
    return boxes


def _jitter(rng: random.Random, boxes: list[AnnotationBox]) -> list[AnnotationBox]:
    moved: list[AnnotationBox] = []
    for box in boxes:
        if rng.random() < 0.15:
            continue
        dx, dy = rng.uniform(-6, 6), rng.uniform(-6, 6)
        category = box.category if rng.random() > 0.1 else rng.choice(LABELS)
        moved.append(
            AnnotationBox(
                category=category, x1=box.x1 + dx, y1=box.y1 + dy, x2=box.x2 + dx, y2=box.y2 + dy
            )
        )
    return moved + _scene(rng, rng.randint(0, 2))


def _record(boxes: list[AnnotationBox]) -> AnnotationRecord:
    return AnnotationRecord(sample_id="s", annotator_id="a", boxes=tuple(boxes))


@pytest.mark.parametrize("seed", range(5))
def test_box_metrics_equal_an_independent_reference_value_by_value(seed: int) -> None:
    """Dense random scenes, near-ties and label flips: every count and ratio is identical."""
    rng = random.Random(seed)  # noqa: S311  # Reproducible geometry, not security.
    pairs: list[tuple[list[AnnotationBox], list[AnnotationBox]]] = []
    for _ in range(40):
        human = _scene(rng, rng.randint(0, 12))
        pairs.append((_jitter(rng, human), human))
    iou_50, iou_75, _ = prelabel_accuracy(
        [(_record(model), _record(human)) for model, human in pairs]
    )
    model_total = sum(len(model) for model, _ in pairs)
    human_total = sum(len(human) for _, human in pairs)
    for result, threshold in ((iou_50, 0.5), (iou_75, 0.75)):
        hits = sum(_reference_hits(model, human, threshold) for model, human in pairs)
        all_hit = sum(
            _reference_hits(model, human, threshold) == len(model) == len(human)
            for model, human in pairs
        )
        assert (result.model_objects, result.human_objects) == (model_total, human_total)
        assert result.true_positives == hits
        assert result.precision == pytest.approx(hits / model_total)
        assert result.recall == pytest.approx(hits / human_total)
        assert result.f1 == pytest.approx(2 * hits / (model_total + human_total))
        assert result.all_hit_tasks == all_hit
