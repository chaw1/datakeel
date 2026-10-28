# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent ratio and leakage invariants for deterministic training stratification."""

from collections import Counter

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRatios, SplitRequest, TrainingSample
from datakeel.training.hashes import normalize_text, simhash
from datakeel.training.splitting import distributions, split_samples


def _sample(index: int, labels: tuple[str, ...] = ()) -> TrainingSample:
    return TrainingSample(
        file=FileItem(
            id=str(index), path="unused", filename=f"{index}.txt", sha256=f"hash-{index}"
        ),
        labels=labels,
    )


def test_single_label_strata_rounding_and_reproducibility() -> None:
    """Every independent category is apportioned within one sample of each ratio."""
    samples = tuple(_sample(index, (f"class-{index % 3}",)) for index in range(307))
    request = SplitRequest(name="baseline", seed=17)
    members = split_samples(samples, request)
    assert members == split_samples(tuple(reversed(samples)), request)
    for distribution in distributions(members):
        for label in distribution.labels:
            total = sum(label.label in sample.labels for sample in samples)
            assert abs(label.count - total * getattr(request.ratios, distribution.split)) <= 1
    assert members != split_samples(samples, request.model_copy(update={"seed": 18}))


def test_multilabel_iterative_stratification_preserves_prevalence() -> None:
    """Iterative assignment balances shared categories rather than whole label tuples."""
    samples = tuple(
        _sample(
            index,
            tuple(label for modulus, label in ((2, "a"), (3, "b"), (5, "c")) if index % modulus),
        )
        for index in range(300)
    )
    request = SplitRequest(name="multilabel")
    members = split_samples(samples, request)
    overall = Counter(label for sample in samples for label in sample.labels)
    for distribution in distributions(members):
        if not distribution.count:
            continue
        for label in distribution.labels:
            assert (
                abs(label.count / distribution.count - overall[label.label] / len(samples)) <= 0.02
            )
            assert (
                abs(
                    label.count - overall[label.label] * getattr(request.ratios, distribution.split)
                )
                <= 1
            )


def test_atomic_transitive_groups_take_priority_over_ratios() -> None:
    """A group link and a duplicate link form a single indivisible connected component."""
    samples = [_sample(index, ("class",)) for index in range(30)]
    samples[0] = samples[0].model_copy(update={"group": "patient"})
    samples[1] = samples[1].model_copy(update={"group": "patient", "image_hash": 123})
    samples[2] = samples[2].model_copy(update={"image_hash": 123})
    members = split_samples(tuple(samples), SplitRequest(name="groups", group_field="patient"))
    assigned = {member.sample_id: member.split for member in members}
    assert len({assigned[str(index)] for index in range(3)}) == 1


def test_group_constraint_applies_when_duplicate_avoidance_is_disabled() -> None:
    """The explicit group guarantee remains active independently of duplicate policy."""
    samples = tuple(_sample(index).model_copy(update={"group": "one"}) for index in range(7))
    members = split_samples(
        samples, SplitRequest(name="groups", avoid_leakage=False, stratify=False)
    )
    assert len({member.split for member in members}) == 1


def test_two_sets_empty_samples_and_directory_validation() -> None:
    """A zero test ratio makes no test assignments and invalid directory metadata fails."""
    request = SplitRequest(name="two", ratios=SplitRatios(train=0.8, val=0.2, test=0))
    members = split_samples(tuple(_sample(index) for index in range(25)), request)
    assert Counter(member.split for member in members) == {"train": 20, "val": 5}
    assert split_samples((), request) == ()
    with pytest.raises(ValidationError, match="split metadata"):
        split_samples((_sample(1),), request.model_copy(update={"source": "directory"}))
    with pytest.raises(ValidationError, match="distinct"):
        split_samples((_sample(1), _sample(1)), request)


def test_simhash_normalizes_punctuation_unicode_case_and_whitespace() -> None:
    """Formatting changes carry exactly the same text signal, while empty text has none."""
    assert simhash("Hello, WORLD! This is a test.") == simhash("  hello world\nthis is a TEST ")
    assert normalize_text("\uff21\uff22\uff23\uff0c甲乙\uff01") == "abc甲乙"
    assert simhash(" \n !!!") is None
    assert simhash("a") != simhash("b")
    assert simhash("A short account of forest conservation.") != simhash(
        "Operating systems allocate virtual address spaces."
    )


@pytest.mark.parametrize("values", [{"train": 0.7}, {"train": 1, "val": 0, "test": 0}])
def test_invalid_ratios_are_rejected(values: dict[str, float]) -> None:
    """Invalid totals and one-partition requests cannot enter persisted split policy."""
    with pytest.raises(ValueError, match="Training split"):
        SplitRatios.model_validate(values)
