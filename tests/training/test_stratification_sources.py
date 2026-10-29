# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Annotation-source selection affects allocation inputs while preserving all frozen facts."""

from collections import Counter

import pytest

from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord, AnnotationSpan
from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRequest, StratificationSource, TrainingSample
from datakeel.training.splitting import distributions, split_samples


def _samples() -> tuple[TrainingSample, ...]:
    return tuple(
        TrainingSample(
            file=FileItem(id=str(index), path="unused", filename=str(index), sha256=str(index)),
            labels=(f"c{index % 2}", f"d{index % 3}", f"s{index % 5}"),
            annotations=(
                AnnotationRecord(
                    sample_id=str(index),
                    annotator_id="reviewer",
                    labels=(f"c{index % 2}",),
                    boxes=(AnnotationBox(category=f"d{index % 3}", x1=0, y1=0, x2=1, y2=1),),
                    spans=(AnnotationSpan(category=f"s{index % 5}", start=0, end=1),),
                ),
            ),
        )
        for index in range(180)
    )


def test_selected_annotation_sources_match_independent_single_kind_strata() -> None:
    """Each source follows that kind's labels and quotas rather than unrelated annotations."""
    samples = _samples()
    sources: tuple[tuple[StratificationSource, str, int], ...] = (
        ("classification", "c", 2),
        ("detection", "d", 3),
        ("spans", "s", 5),
    )
    originals = {sample.file.id: sample for sample in samples}
    for source, prefix, categories in sources:
        request = SplitRequest(name="selected", seed=17, stratification_source=source)
        actual = split_samples(samples, request)
        reference = tuple(
            sample.model_copy(update={"labels": (f"{prefix}{index % categories}",)})
            for index, sample in enumerate(samples)
        )
        expected = split_samples(
            reference, request.model_copy(update={"stratification_source": "all"})
        )
        assert [(member.sample_id, member.split) for member in actual] == [
            (member.sample_id, member.split) for member in expected
        ]
        assert all(member.labels == originals[member.sample_id].labels for member in actual)
        assert all(
            member.annotations == originals[member.sample_id].annotations for member in actual
        )
        for row in distributions(actual):
            counts = Counter(
                label
                for member in actual
                if member.split == row.split
                for label in member.labels
                if label.startswith(prefix)
            )
            target = len(samples) / categories * getattr(request.ratios, row.split)
            assert all(
                abs(counts[f"{prefix}{category}"] - target) <= 1 for category in range(categories)
            )
            assert len(row.labels) == 10


def test_default_all_keeps_label_only_samples_and_original_annotation_order() -> None:
    """Legacy internal samples need no annotations when the source policy remains all."""
    samples = tuple(sample.model_copy(update={"annotations": ()}) for sample in _samples())
    implicit = SplitRequest(name="all", seed=11)
    assert implicit.stratification_source == "all"
    assert split_samples(samples, implicit) == split_samples(
        samples, implicit.model_copy(update={"stratification_source": "all"})
    )


def test_selected_kind_retains_multiple_labels_from_all_frozen_annotators() -> None:
    """Selecting classification preserves its multilabel union across independent reviews."""
    samples = tuple(
        sample.model_copy(
            update={
                "labels": (*sample.labels, f"extra{index % 3}"),
                "annotations": (
                    *sample.annotations,
                    AnnotationRecord(
                        sample_id=sample.file.id,
                        annotator_id="second-reviewer",
                        labels=(f"extra{index % 3}",),
                    ),
                ),
            }
        )
        for index, sample in enumerate(_samples())
    )
    reference = tuple(
        sample.model_copy(update={"labels": (f"c{index % 2}", f"extra{index % 3}")})
        for index, sample in enumerate(samples)
    )
    actual = split_samples(
        samples, SplitRequest(name="multilabel", stratification_source="classification")
    )
    expected = split_samples(reference, SplitRequest(name="multilabel"))
    assert [(member.sample_id, member.split) for member in actual] == [
        (member.sample_id, member.split) for member in expected
    ]


def test_missing_selected_annotations_are_unlabelled_without_falling_back_to_other_kinds() -> None:
    """A missing or reviewed-empty selected kind contributes no labels to allocation."""
    samples = tuple(
        sample.model_copy(
            update={"annotations": (sample.annotations[0].model_copy(update={"labels": None}),)}
        )
        for sample in _samples()
    )
    request = SplitRequest(name="missing", stratification_source="classification")
    actual = split_samples(samples, request)
    reference = tuple(sample.model_copy(update={"labels": ()}) for sample in samples)
    expected = split_samples(reference, request.model_copy(update={"stratification_source": "all"}))
    assert [(member.sample_id, member.split) for member in actual] == [
        (member.sample_id, member.split) for member in expected
    ]
    assert all(member.labels for member in actual)


def test_source_selection_preserves_atomic_groups_and_directory_or_disabled_policies() -> None:
    """Source kinds never split groups, discard frozen reviews or override directory assignments."""
    samples = tuple(
        sample.model_copy(
            update={
                "group": "together" if index < 4 else None,
                "file": sample.file.model_copy(update={"metadata": {"split": "train"}}),
            }
        )
        for index, sample in enumerate(_samples()[:20])
    )
    for source in ("all", "classification", "detection", "spans"):
        request = SplitRequest(name="groups", stratification_source=source)
        members = split_samples(samples, request)
        assert len({member.split for member in members if int(member.sample_id) < 4}) == 1
        assert all(
            member.split == "train"
            for member in split_samples(samples, request.model_copy(update={"source": "directory"}))
        )
        assert split_samples(
            samples, request.model_copy(update={"stratify": False})
        ) == split_samples(samples, SplitRequest(name="groups", stratify=False))


def test_unknown_stratification_source_is_rejected_at_the_typed_boundary() -> None:
    """Callers cannot silently select an undeclared annotation source."""
    with pytest.raises(ValueError, match="stratification_source"):
        SplitRequest.model_validate({"name": "invalid", "stratification_source": "boxes"})
