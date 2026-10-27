# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared deterministic grouping for pure annotation review algorithms."""

from collections import defaultdict
from itertools import combinations

from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord


def sample_groups(batch: AnnotationBatch) -> tuple[tuple[AnnotationRecord, ...], ...]:
    """Group ratings by sorted sample identity and annotator identity."""
    grouped: dict[str, list[AnnotationRecord]] = defaultdict(list)
    for item in batch.annotations:
        grouped[item.sample_id].append(item)
    return tuple(
        tuple(sorted(grouped[key], key=lambda item: item.annotator_id)) for key in sorted(grouped)
    )


def paired_records(
    batch: AnnotationBatch,
) -> tuple[tuple[str, str, tuple[tuple[AnnotationRecord, AnnotationRecord], ...]], ...]:
    """Group shared sample records by sorted annotator pair without imputing missing work."""
    pairs: dict[tuple[str, str], list[tuple[AnnotationRecord, AnnotationRecord]]] = defaultdict(
        list
    )
    for group in sample_groups(batch):
        for a, b in combinations(group, 2):
            pairs[a.annotator_id, b.annotator_id].append((a, b))
    return tuple((a, b, tuple(pairs[a, b])) for a, b in sorted(pairs))
