# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Panel consensus for boxes and spans: category or boundary minority, missing and extra items.

Items from different annotators on one sample are matched one-to-one per annotator
pair by descending similarity, then joined into clusters. A cluster supported by a
strict majority of the sample's panel is a consensus object; panel members without
it are reported as missing it, and members whose category (or span offsets) differ
from the cluster's strict majority are reported as the minority. An item that only
its own annotator drew, while at least two other panel members reviewed the same
modality, is reported as extra. At least three panel members are required.
Invalid items are reported by the bounds rules instead; an annotator whose record
holds an invalid item of the consensus category is not also reported as missing it.
Additional items by one annotator in a cluster are reported as duplicates. Each
annotator casts at most one vote per value; conflicting values from one annotator
abstain while that annotator remains in the strict-majority denominator.
"""

from collections import Counter, defaultdict
from collections.abc import Callable
from itertools import combinations
from typing import NamedTuple

from datakeel.annotation_qa.findings import box_is_valid, finding, span_is_valid
from datakeel.annotation_qa.geometry import box_iou
from datakeel.annotation_qa.grouping import sample_groups
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationFinding,
    AnnotationRecord,
    FindingCode,
)

_MIN_PANEL = 3


class _Item(NamedTuple):
    record: AnnotationRecord
    position: int
    category: str
    shape: tuple[float, ...]


class _Panel(NamedTuple):
    record: AnnotationRecord
    items: list[_Item]
    invalid_categories: frozenset[str]


class _Rules(NamedTuple):
    noun: str
    missing: FindingCode
    extra: FindingCode
    category: FindingCode
    boundary: FindingCode | None
    duplicate: FindingCode


_BOX_RULES = _Rules(
    "box", "bbox_missing", "bbox_extra", "bbox_category_minority", None, "duplicate_bbox"
)
_SPAN_RULES = _Rules(
    "span",
    "span_missing",
    "span_extra",
    "span_category_minority",
    "span_boundary_minority",
    "duplicate_span",
)


def span_jaccard(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Return intersection over union of two half-open character intervals."""
    overlap = min(left[1], right[1]) - max(left[0], right[0])
    if overlap <= 0:
        return 0
    return overlap / (max(left[1], right[1]) - min(left[0], right[0]))


def _box_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return box_iou(
        AnnotationBox(category="", x1=left[0], y1=left[1], x2=left[2], y2=left[3]),
        AnnotationBox(category="", x1=right[0], y1=right[1], x2=right[2], y2=right[3]),
    )


def _find(parent: dict[int, int], node: int) -> int:
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


def _clusters(
    panel: dict[str, _Panel],
    similarity: Callable[[tuple[float, ...], tuple[float, ...]], float],
    threshold: float,
) -> list[list[_Item]]:
    items = [item for annotator in sorted(panel) for item in panel[annotator].items]
    position = {
        (item.record.annotator_id, item.position): offset for offset, item in enumerate(items)
    }
    parent = {offset: offset for offset in range(len(items))}
    for left, right in combinations(sorted(panel), 2):
        scored = sorted(
            (
                (similarity(a.shape, b.shape), a.position, b.position)
                for a in panel[left].items
                for b in panel[right].items
            ),
            key=lambda value: (-value[0], value[1], value[2]),
        )
        used_left: set[int] = set()
        used_right: set[int] = set()
        for score, i, j in scored:
            if score >= threshold and score > 0 and i not in used_left and j not in used_right:
                used_left.add(i)
                used_right.add(j)
                a, b = _find(parent, position[left, i]), _find(parent, position[right, j])
                parent[max(a, b)] = min(a, b)
    grouped: dict[int, list[_Item]] = defaultdict(list)
    for offset, item in enumerate(items):
        grouped[_find(parent, offset)].append(item)
    return [grouped[key] for key in sorted(grouped)]


def _describe(item: _Item) -> str:
    shape = ",".join(f"{value:g}" for value in item.shape)
    return f"{item.record.annotator_id}[{item.position}] {item.category} @ {shape}"


def _votes(members: list[_Item], value: Callable[[_Item], str]) -> Counter[str]:
    choices: dict[str, set[str]] = defaultdict(set)
    for item in members:
        choices[item.record.annotator_id].add(value(item))
    return Counter(next(iter(values)) for values in choices.values() if len(values) == 1)


def _cluster_duplicates(members: list[_Item], rules: _Rules) -> list[AnnotationFinding]:
    first: dict[str, _Item] = {}
    result: list[AnnotationFinding] = []
    for item in members:
        annotator = item.record.annotator_id
        if annotator not in first:
            first[annotator] = item
            continue
        original = first[annotator]
        result.append(
            finding(
                item.record,
                rules.duplicate,
                f"The same annotator contributed multiple items to one {rules.noun} cluster",
                (f"retained: {_describe(original)}", f"additional: {_describe(item)}"),
                key=str(item.position),
            )
        )
    return result


def _minority(
    members: list[_Item], value: Callable[[_Item], str], code: FindingCode, noun: str
) -> list[AnnotationFinding]:
    counts = _votes(members, value)
    if not counts:
        return []
    majority, votes = counts.most_common(1)[0]
    total = len({item.record.annotator_id for item in members})
    if votes * 2 <= total:
        return []
    return [
        finding(
            item.record,
            code,
            f"Matched {noun} differs from the strict majority of the annotator panel",
            (
                f"majority={majority}; votes={votes}/{total}",
                f"observed={value(item)}; {_describe(item)}",
            ),
            key=str(item.position),
        )
        for item in members
        if value(item) != majority
    ]


def _cluster_findings(
    members: list[_Item], panel: dict[str, _Panel], rules: _Rules
) -> list[AnnotationFinding]:
    annotators = {item.record.annotator_id for item in members}
    representative = min(members, key=lambda item: (item.record.annotator_id, item.position))
    categories = _votes(members, lambda item: item.category)
    category = categories.most_common(1)[0][0] if categories else None
    result = _cluster_duplicates(members, rules)
    if len(annotators) * 2 > len(panel):
        absent = [
            annotator
            for annotator in sorted(set(panel) - annotators)
            if category not in panel[annotator].invalid_categories
        ]
        result.extend(
            finding(
                panel[annotator].record,
                rules.missing,
                f"A {rules.noun} drawn by a strict majority of the panel is absent here",
                (
                    f"support={len(annotators)}/{len(panel)}",
                    f"consensus example: {_describe(representative)}",
                ),
                key=f"{representative.record.annotator_id}#{representative.position}",
            )
            for annotator in absent
        )
        result.extend(_minority(members, lambda item: item.category, rules.category, rules.noun))
        if rules.boundary is not None:
            result.extend(
                _minority(
                    members,
                    lambda item: ":".join(f"{value:g}" for value in item.shape),
                    rules.boundary,
                    rules.noun,
                )
            )
    elif len(annotators) == 1:
        result.extend(
            finding(
                item.record,
                rules.extra,
                f"No other panel member drew an overlapping {rules.noun}",
                (f"support=1/{len(panel)}", _describe(item)),
                key=str(item.position),
            )
            for item in members
        )
    return result


def _panel_findings(
    batch: AnnotationBatch,
    items: Callable[[AnnotationRecord], _Panel | None],
    similarity: Callable[[tuple[float, ...], tuple[float, ...]], float],
    threshold: float,
    rules: _Rules,
) -> tuple[AnnotationFinding, ...]:
    result: list[AnnotationFinding] = []
    for group in sample_groups(batch):
        panel = {
            record.annotator_id: values for record in group if (values := items(record)) is not None
        }
        if len(panel) < _MIN_PANEL:
            continue
        for members in _clusters(panel, similarity, threshold):
            result.extend(_cluster_findings(members, panel, rules))
    return tuple(result)


def _boxes(record: AnnotationRecord) -> _Panel | None:
    if record.boxes is None:
        return None
    return _Panel(
        record,
        [
            _Item(record, index, box.category, (box.x1, box.y1, box.x2, box.y2))
            for index, box in enumerate(record.boxes)
            if box_is_valid(record, box)
        ],
        frozenset(box.category for box in record.boxes if not box_is_valid(record, box)),
    )


def _spans(record: AnnotationRecord) -> _Panel | None:
    if record.spans is None:
        return None
    return _Panel(
        record,
        [
            _Item(record, index, span.category, (span.start, span.end))
            for index, span in enumerate(record.spans)
            if span_is_valid(record, span)
        ],
        frozenset(span.category for span in record.spans if not span_is_valid(record, span)),
    )


def consensus_findings(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Compare every box and span with the panel consensus of its sample."""
    return (
        *_panel_findings(batch, _boxes, _box_similarity, batch.iou_threshold, _BOX_RULES),
        *_panel_findings(batch, _spans, span_jaccard, 0, _SPAN_RULES),
    )
