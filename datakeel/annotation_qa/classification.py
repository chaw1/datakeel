# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Class-label agreement and binary per-class confusion projections."""

from datakeel.annotation_qa.categorical import cohen_kappa, fleiss_kappa, krippendorff_alpha
from datakeel.annotation_qa.grouping import paired_records, sample_groups
from datakeel.core.annotation_models import (
    AnnotationBatch,
    ClassConfusion,
    ClassificationAgreement,
    ClassificationPair,
)


def _confusion(
    pairs: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...],
) -> tuple[ClassConfusion, ...]:
    labels = sorted({label for pair in pairs for rating in pair for label in rating})
    return tuple(
        ClassConfusion(
            category=label,
            true_positive=sum(label in a and label in b for a, b in pairs),
            false_positive=sum(label not in a and label in b for a, b in pairs),
            false_negative=sum(label in a and label not in b for a, b in pairs),
            true_negative=sum(label not in a and label not in b for a, b in pairs),
        )
        for label in labels
    )


def nominal_name(labels: tuple[str, ...]) -> str:
    """Name one canonical label set as a single nominal category."""
    return "+".join(labels) if labels else "(empty)"


def confusion_matrix(
    pairs: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...],
) -> tuple[tuple[str, ...], tuple[tuple[int, ...], ...]]:
    """Count paired nominal categories; rows are the left annotator, columns the right."""
    names = tuple(sorted({nominal_name(rating) for pair in pairs for rating in pair}))
    position = {name: index for index, name in enumerate(names)}
    matrix = [[0] * len(names) for _ in names]
    for left, right in pairs:
        matrix[position[nominal_name(left)]][position[nominal_name(right)]] += 1
    return names, tuple(tuple(row) for row in matrix)


def classification_agreement(batch: AnnotationBatch) -> ClassificationAgreement:
    """Treat each unique sorted multilabel set as one nominal category."""
    panels = [
        [None if item.labels is None else tuple(sorted(set(item.labels))) for item in group]
        for group in sample_groups(batch)
        if any(item.labels is not None for item in group)
    ]
    result: list[ClassificationPair] = []
    for a, b, records in paired_records(batch):
        pairs = tuple(
            (tuple(sorted(set(left.labels))), tuple(sorted(set(right.labels))))
            for left, right in records
            if left.labels is not None and right.labels is not None
        )
        if not pairs:
            continue
        categories, matrix = confusion_matrix(pairs)
        result.append(
            ClassificationPair(
                annotator_a=a,
                annotator_b=b,
                cohen_kappa=cohen_kappa([p[0] for p in pairs], [p[1] for p in pairs]),
                confusion=_confusion(pairs),
                categories=categories,
                matrix=matrix,
            )
        )
    return ClassificationAgreement(
        pairs=tuple(result),
        fleiss_kappa=fleiss_kappa(panels),
        krippendorff_alpha=krippendorff_alpha(panels),
    )
