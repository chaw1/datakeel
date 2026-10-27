# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Batch-level label statistics: multi-select conflicts and singleton categories.

A record is a multi-select conflict when it combines labels that are declared
mutually exclusive, when the batch is declared single-select, when the batch
behaves as single-select (at most 1% of at least 20 labelled records carry more
than one label), or when two otherwise frequent labels almost never co-occur
(co-occurrence in at most 2% of the rarer label's records although independence
predicts at least five). A label, box category or span category used exactly once
in a batch of at least 50 such annotations is reported as a rare category, which
catches typing errors without a vocabulary.
"""

import json
from collections import Counter
from itertools import combinations

from datakeel.annotation_qa.findings import finding
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationFinding,
    AnnotationRecord,
)

_MIN_SINGLE_SELECT_RECORDS = 20
_SINGLE_SELECT_PERCENT = 1
_MIN_EXPECTED_COOCCURRENCE = 5
_COOCCURRENCE_RATIO = 50
_MIN_RARE_POPULATION = 50


def _label_sets(batch: AnnotationBatch) -> list[tuple[AnnotationRecord, tuple[str, ...]]]:
    return [
        (item, tuple(sorted(set(item.labels))))
        for item in batch.annotations
        if item.labels is not None
    ]


def _single_select_reason(
    batch: AnnotationBatch, rated: list[tuple[AnnotationRecord, tuple[str, ...]]]
) -> str | None:
    if batch.label_mode == "single":
        return "batch label_mode=single"
    labelled = [labels for _, labels in rated if labels]
    multiple = sum(len(labels) > 1 for labels in labelled)
    if (
        batch.label_mode == "auto"
        and len(labelled) >= _MIN_SINGLE_SELECT_RECORDS
        and multiple * 100 <= len(labelled) * _SINGLE_SELECT_PERCENT
    ):
        return f"batch behaves as single-select: {multiple}/{len(labelled)} records have >1 label"
    return None


def _cooccurrence_reasons(
    rated: list[tuple[AnnotationRecord, tuple[str, ...]]],
) -> dict[tuple[str, str], str]:
    total = len(rated)
    singles = Counter(label for _, labels in rated for label in labels)
    pairs = Counter(pair for _, labels in rated for pair in combinations(labels, 2))
    reasons: dict[tuple[str, str], str] = {}
    for (left, right), together in pairs.items():
        expected = singles[left] * singles[right] / total
        rarer = min(singles[left], singles[right])
        if expected >= _MIN_EXPECTED_COOCCURRENCE and together * _COOCCURRENCE_RATIO <= rarer:
            reasons[left, right] = (
                f"{left}+{right} co-occur in {together}/{total} records; "
                f"independence predicts {expected:.1f}; "
                f"{left}={singles[left]}, {right}={singles[right]}"
            )
    return reasons


def multiselect_findings(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Flag records whose label set breaks declared or observed exclusivity."""
    rated = _label_sets(batch)
    single = _single_select_reason(batch, rated)
    cooccurrence = _cooccurrence_reasons(rated) if rated else {}
    result: list[AnnotationFinding] = []
    for record, labels in rated:
        if len(labels) < 2:  # noqa: PLR2004  # A conflict needs two labels.
            continue
        evidence = [
            f"declared exclusive group={sorted(set(group))}"
            for group in batch.exclusive_label_groups
            if len(set(labels) & set(group)) > 1
        ]
        evidence.extend(
            cooccurrence[pair] for pair in combinations(labels, 2) if pair in cooccurrence
        )
        if single is not None:
            evidence.append(single)
        if evidence:
            result.append(
                finding(
                    record,
                    "multilabel_conflict",
                    "One sample carries labels that this batch treats as mutually exclusive",
                    (f"labels={json.dumps(labels, ensure_ascii=False)}", *evidence),
                )
            )
    return tuple(result)


def _rare(
    observations: list[tuple[AnnotationRecord, str, str]], noun: str
) -> list[AnnotationFinding]:
    counts = Counter(category for _, _, category in observations)
    if len(observations) < _MIN_RARE_POPULATION:
        return []
    return [
        finding(
            record,
            "rare_category",
            f"This {noun} category occurs only once in the batch; check for a typing error",
            (f"{noun}={category!r}; occurrences=1/{len(observations)}", f"location={location}"),
            key=f"{noun}:{location}",
        )
        for record, location, category in observations
        if counts[category] == 1
    ]


def rare_category_findings(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Flag labels, box categories and span categories that occur exactly once."""
    labels = [
        (record, label, label)
        for record in batch.annotations
        for label in sorted(set(record.labels or ()))
    ]
    boxes = [
        (record, f"box[{index}]", box.category)
        for record in batch.annotations
        for index, box in enumerate(record.boxes or ())
    ]
    spans = [
        (record, f"span[{index}]", span.category)
        for record in batch.annotations
        for index, span in enumerate(record.spans or ())
    ]
    return (*_rare(labels, "label"), *_rare(boxes, "box"), *_rare(spans, "span"))
