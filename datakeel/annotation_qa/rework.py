# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable repair queues and same-policy before/after review comparisons."""

import csv
import io
import json
from collections import defaultdict

from datakeel.annotation_qa.service import find_suspicions
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationFinding,
    AnnotationRecord,
    ReworkComparison,
)


def _retained(before: AnnotationRecord, after: AnnotationRecord | None) -> bool:
    if after is None:
        return False
    return all(
        old is None or new is not None
        for old, new in (
            (before.labels, after.labels),
            (before.boxes, after.boxes),
            (before.spans, after.spans),
        )
    )


def _assessed(
    candidate: AnnotationFinding, before: AnnotationBatch, after: AnnotationBatch
) -> bool:
    affected = {candidate.sample_id, *candidate.related_sample_ids}
    remaining = {(item.sample_id, item.annotator_id): item for item in after.annotations}
    return all(
        _retained(item, remaining.get((item.sample_id, item.annotator_id)))
        for item in before.annotations
        if item.sample_id in affected
    )


def _carried(
    original: dict[str, AnnotationFinding], current: dict[str, AnnotationFinding]
) -> set[str]:
    """Pair unmatched findings that only moved to another item position in the same record.

    Item findings are keyed by position, so deleting or inserting an unrelated box or
    span renumbers the rest of that annotator's items. An unmatched old finding and an
    unmatched new finding with the same sample, annotator, rule and related samples
    are therefore one unresolved issue, never a correction plus a regression.
    """
    groups: dict[tuple[object, ...], tuple[list[str], list[str]]] = defaultdict(lambda: ([], []))
    for side, findings, other in ((0, original, current), (1, current, original)):
        for key, item in sorted(findings.items()):
            if key not in other:
                identity = (item.sample_id, item.annotator_id, item.code, item.related_sample_ids)
                groups[identity][side].append(key)
    return {
        key for old, new in groups.values() for pair in zip(old, new, strict=False) for key in pair
    }


def compare_rework(before: AnnotationBatch, after: AnnotationBatch) -> ReworkComparison:
    """Compare stable finding identities, keeping removed work explicitly unassessed.

    Review policy and near-duplicate relations must be preserved so suppressing a
    rule cannot count as repair. Missing annotations or peers never count as fixed.
    A finding renumbered by an unrelated edit of the same record stays remaining.
    """
    if (
        before.exclusive_label_groups != after.exclusive_label_groups
        or before.near_duplicates != after.near_duplicates
        or before.iou_threshold != after.iou_threshold
        or before.label_mode != after.label_mode
        or before.outlier_policy != after.outlier_policy
    ):
        message = "Rework comparisons require unchanged review policy and duplicate relations"
        raise ValueError(message)
    original = {item.finding_id: item for item in find_suspicions(before)}
    current = {item.finding_id: item for item in find_suspicions(after)}
    carried = _carried(original, current)
    unresolved = tuple(
        item for key, item in original.items() if key not in current and key not in carried
    )
    corrected = tuple(item for item in unresolved if _assessed(item, before, after))
    unassessed = tuple(item for item in unresolved if not _assessed(item, before, after))
    introduced = tuple(
        item for key, item in current.items() if key not in original and key not in carried
    )
    remaining = tuple(item for key, item in current.items() if key in original or key in carried)
    old = {(item.sample_id, item.annotator_id): item for item in before.annotations}
    new = {(item.sample_id, item.annotator_id): item for item in after.annotations}
    shared = old.keys() & new.keys()
    changed = sum(old[key] != new[key] for key in shared)
    return ReworkComparison(
        before_count=len(original),
        after_count=len(current),
        corrected_count=len(corrected),
        introduced_count=len(introduced),
        remaining_count=len(remaining),
        unassessed_count=len(unassessed),
        changed_records=changed,
        unchanged_records=len(shared) - changed,
        added_records=len(new.keys() - old.keys()),
        removed_records=len(old.keys() - new.keys()),
        corrected=corrected,
        introduced=introduced,
        remaining=remaining,
        unassessed=unassessed,
    )


def changed_samples(before: AnnotationBatch, after: AnnotationBatch) -> frozenset[str]:
    """Return samples with any added, removed or modified sample/annotator record."""
    old = {(item.sample_id, item.annotator_id): item for item in before.annotations}
    new = {(item.sample_id, item.annotator_id): item for item in after.annotations}
    return frozenset(key[0] for key in old.keys() | new.keys() if old.get(key) != new.get(key))


def _spreadsheet_cell(value: str) -> str:
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value


def export_rework_csv(findings: tuple[AnnotationFinding, ...]) -> str:
    """Export UTF-8-compatible RFC 4180 rows, guarding spreadsheet formula prefixes."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["finding_id", "sample_id", "annotator_id", "code", "reason", "evidence"])
    for item in findings:
        writer.writerow(
            [
                _spreadsheet_cell(value)
                for value in (
                    item.finding_id,
                    item.sample_id,
                    item.annotator_id,
                    item.code,
                    item.reason,
                    json.dumps(item.evidence, ensure_ascii=False),
                )
            ]
        )
    return output.getvalue()


def export_rework_json(findings: tuple[AnnotationFinding, ...]) -> str:
    """Export structured repair evidence without flattening nested evidence lists."""
    return json.dumps(
        [item.model_dump(mode="json") for item in findings], ensure_ascii=False, indent=2
    )
