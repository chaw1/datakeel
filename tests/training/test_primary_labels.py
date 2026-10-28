# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical primary labels affect allocation without discarding source annotations."""

from collections import Counter

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRequest, TrainingSample
from datakeel.training.splitting import distributions, split_samples


def test_primary_label_order_is_canonical_and_full_annotations_are_preserved() -> None:
    """Reversing label order changes neither membership nor the retained annotation facts."""
    samples = tuple(
        TrainingSample(
            file=FileItem(
                id=f"{label}-{index}", path="unused", filename=str(index), sha256=f"{label}-{index}"
            ),
            labels=("z", label),
            annotations=(
                AnnotationRecord(
                    sample_id=f"{label}-{index}", annotator_id="reviewer", labels=("z", label)
                ),
            ),
        )
        for label, count in (("a", 55), ("b", 52), ("c", 52))
        for index in range(count)
    )
    request = SplitRequest(name="primary", seed=7)
    members = split_samples(samples, request)
    reordered = split_samples(
        tuple(
            sample.model_copy(update={"labels": tuple(reversed(sample.labels))})
            for sample in reversed(samples)
        ),
        request,
    )
    assert [(member.sample_id, member.split) for member in members] == [
        (member.sample_id, member.split) for member in reordered
    ]
    originals = {sample.file.id: sample for sample in samples}
    assert all(
        member.labels == originals[member.sample_id].labels
        and member.annotations == originals[member.sample_id].annotations
        for member in members
    )
    totals = Counter(min(sample.labels) for sample in samples)
    for row in distributions(members):
        primary = Counter(min(member.labels) for member in members if member.split == row.split)
        assert all(
            abs(primary[label] - count * getattr(request.ratios, row.split)) <= 1 + 1e-9
            and abs(primary[label] / row.count - count / len(samples)) <= 0.02 + 1e-9
            for label, count in totals.items()
        )
        assert next(label.count for label in row.labels if label.label == "z") == row.count
