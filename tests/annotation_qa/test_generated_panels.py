# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated three-annotator panels: every planted error type is found, clean data stays quiet."""

from collections.abc import Callable
from typing import Literal

import numpy as np
import pytest

from datakeel.annotation_qa import find_suspicions
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
    NearDuplicatePair,
)

ANNOTATORS = ("a", "b", "c")
WIDTH, HEIGHT = 640, 480
type Sizes = Literal["lognormal", "uniform", "tight"]
type Edit = Callable[[AnnotationRecord], AnnotationRecord]


def _size(rng: np.random.Generator, sizes: Sizes) -> tuple[float, float]:
    if sizes == "lognormal":
        return float(np.exp(rng.normal(4, 0.4))), float(np.exp(rng.normal(3.8, 0.4)))
    if sizes == "uniform":
        return float(rng.uniform(20, 200)), float(rng.uniform(20, 200))
    return float(rng.uniform(45, 55)), float(rng.uniform(45, 55))


def _sample(
    rng: np.random.Generator, index: int, sizes: Sizes, labels: tuple[str, ...]
) -> list[AnnotationRecord]:
    objects = []
    for _ in range(int(rng.integers(1, 5))):
        width, height = _size(rng, sizes)
        x, y = rng.uniform(0, WIDTH - width - 5), rng.uniform(0, HEIGHT - height - 5)
        objects.append((("car", "person", "sign")[int(rng.integers(3))], x, y, width, height))
    spans, cursor = [], 0
    for _ in range(int(rng.integers(1, 4))):
        start = cursor + int(rng.integers(1, 20))
        cursor = start + int(rng.integers(3, 15))
        spans.append(
            AnnotationSpan(category=("PER", "ORG", "LOC")[rng.integers(3)], start=start, end=cursor)
        )
    label = (labels[int(rng.integers(len(labels)))],)
    records = []
    for annotator in ANNOTATORS:
        jitter = rng.normal(0, 1.5, size=(len(objects), 4))
        boxes = tuple(
            AnnotationBox(
                category=category,
                x1=max(0, x + dx1),
                y1=max(0, y + dy1),
                x2=min(WIDTH, x + width + dx2),
                y2=min(HEIGHT, y + height + dy2),
            )
            for (category, x, y, width, height), (dx1, dy1, dx2, dy2) in zip(
                objects, jitter, strict=True
            )
        )
        records.append(
            AnnotationRecord(
                sample_id=f"s{index:03d}",
                annotator_id=annotator,
                labels=label,
                boxes=boxes,
                spans=tuple(spans),
                text_length=cursor + 20,
                image_width=WIDTH,
                image_height=HEIGHT,
            )
        )
    return records


def _clean(seed: int, sizes: Sizes, labels: tuple[str, ...]) -> AnnotationBatch:
    rng = np.random.default_rng(seed)
    records = [record for index in range(200) for record in _sample(rng, index, sizes, labels)]
    for index in range(1, 20, 2):
        twin = records[3 * (index - 1)].labels
        for offset in range(3):
            records[3 * index + offset] = records[3 * index + offset].model_copy(
                update={"labels": twin}
            )
    pairs = tuple(
        NearDuplicatePair(sample_id=f"s{index:03d}", other_sample_id=f"s{index + 1:03d}")
        for index in range(0, 20, 2)
    )
    return AnnotationBatch(annotations=tuple(records), near_duplicates=pairs)


def _first_box(change: Callable[[AnnotationBox], AnnotationBox]) -> Edit:
    return lambda record: record.model_copy(
        update={"boxes": (change((record.boxes or ())[0]), *(record.boxes or ())[1:])}
    )


def _first_span(change: Callable[[AnnotationSpan], AnnotationSpan]) -> Edit:
    return lambda record: record.model_copy(
        update={"spans": (change((record.spans or ())[0]), *(record.spans or ())[1:])}
    )


def _scaled(box: AnnotationBox, factor: float) -> AnnotationBox:
    width, height = (box.x2 - box.x1) * factor, (box.y2 - box.y1) * factor
    centre_x, centre_y = (box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2
    return box.model_copy(
        update={
            "x1": max(0, centre_x - width / 2),
            "y1": max(0, centre_y - height / 2),
            "x2": min(WIDTH, centre_x + width / 2),
            "y2": min(HEIGHT, centre_y + height / 2),
        }
    )


def _relabel(record: AnnotationRecord) -> AnnotationRecord:
    current = (record.labels or ("cat",))[0]
    return record.model_copy(update={"labels": ("dog",) if current != "dog" else ("cat",)})


EDITS: dict[str, Edit] = {
    "minority label": _relabel,
    "single-select conflict": lambda r: r.model_copy(
        update={"labels": tuple(sorted({*(r.labels or ()), "dog", "cat"}))}
    ),
    "box too large": _first_box(lambda box: _scaled(box, 2.5)),
    "box too small": _first_box(lambda box: _scaled(box, 0.25)),
    "box aspect": _first_box(
        lambda box: box.model_copy(update={"y2": box.y1 + (box.y2 - box.y1) / 6})
    ),
    "box category": _first_box(lambda box: box.model_copy(update={"category": "truck"})),
    "box outside image": _first_box(lambda box: box.model_copy(update={"x2": WIDTH + 40})),
    "box missing": lambda r: r.model_copy(update={"boxes": (r.boxes or ())[1:]}),
    "box extra": lambda r: r.model_copy(
        update={
            "boxes": (*(r.boxes or ()), AnnotationBox(category="car", x1=600, y1=5, x2=630, y2=40))
        }
    ),
    "box duplicate": lambda r: r.model_copy(
        update={"boxes": (*(r.boxes or ()), (r.boxes or ())[0])}
    ),
    "span boundary": _first_span(lambda span: span.model_copy(update={"end": span.end + 3})),
    "span category": _first_span(lambda span: span.model_copy(update={"category": "MISC"})),
    "span outside text": _first_span(lambda span: span.model_copy(update={"end": 10_000})),
    "span missing": lambda r: r.model_copy(update={"spans": (r.spans or ())[1:]}),
}


@pytest.mark.parametrize("sizes", ["lognormal", "uniform", "tight"])
def test_every_planted_error_type_is_found(sizes: Sizes) -> None:
    """Fourteen per-annotator error types and a near-duplicate conflict are all reported."""
    batch = _clean(11, sizes, ("cat", "dog", "bird"))
    records = {(item.sample_id, item.annotator_id): item for item in batch.annotations}
    planted: dict[str, str] = {}
    for offset, (name, edit) in enumerate(EDITS.items()):
        sample = f"s{40 + 7 * offset:03d}"
        records[sample, "c"] = edit(records[sample, "c"])
        planted[name] = sample
    for annotator in ANNOTATORS:
        records["s001", annotator] = _relabel(records["s001", annotator])
    findings = find_suspicions(batch.model_copy(update={"annotations": tuple(records.values())}))
    reported = {(item.sample_id, item.annotator_id) for item in findings}
    missed = [name for name, sample in planted.items() if (sample, "c") not in reported]
    assert missed == []
    assert any(
        item.code == "near_duplicate_conflict" and item.sample_id == "s001" for item in findings
    )


@pytest.mark.parametrize("sizes", ["lognormal", "uniform", "tight"])
@pytest.mark.parametrize("seed", [1, 2])
def test_clean_panels_have_at_most_two_percent_flagged_samples(sizes: Sizes, seed: int) -> None:
    """Agreeing jittered panels with honest size tails stay under the 2% budget."""
    findings = find_suspicions(_clean(seed, sizes, ("cat", "dog", "bird", "fish")))
    assert len({item.sample_id for item in findings}) / 200 <= 0.02
    assert len(findings) / 600 <= 0.02
