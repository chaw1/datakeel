# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent feasibility checks for small single-label integer allocation."""

from collections import Counter

from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitName, SplitRatios, SplitRequest, TrainingSample
from datakeel.training.single_prevalence import balance_single_labels
from datakeel.training.splitting import distributions, split_samples


def _samples(counts: tuple[int, ...]) -> tuple[TrainingSample, ...]:
    return tuple(
        TrainingSample(
            file=FileItem(
                id=f"{label}-{index}", filename=str(index), path="unused", sha256=f"{label}-{index}"
            ),
            labels=(str(label),),
        )
        for label, count in enumerate(counts)
        for index in range(count)
    )


def test_integer_solver_reassigns_large_errors_without_violating_class_limits() -> None:
    """The bounded transport solution can recover from a fully concentrated initial state."""
    samples = _samples((82, 76, 63, 65, 52, 53, 50, 58))
    request = SplitRequest(name="transport", ratios=SplitRatios(train=0.9, val=0.05, test=0.05))
    initial: dict[int, SplitName] = dict.fromkeys(range(len(samples)), "train")
    result = balance_single_labels(samples, initial, request)
    totals = Counter(sample.labels[0] for sample in samples)
    for split in ("train", "val", "test"):
        selected = [sample for index, sample in enumerate(samples) if result[index] == split]
        counts = Counter(sample.labels[0] for sample in selected)
        assert selected
        for label, total in totals.items():
            assert abs(counts[label] - total * getattr(request.ratios, split)) <= 1 + 1e-9
            assert abs(counts[label] / len(selected) - total / len(samples)) <= 0.02 + 1e-9


def test_small_ratio_constraints_can_be_proved_numerically_unattainable() -> None:
    """Some positive set sizes admit no integer count inside both specified error bounds."""
    counts = (92, 83, 68)
    population = sum(counts)
    possible = [
        size
        for size in range(1, population + 1)
        if all(
            any(
                abs(value - count * 0.05) <= 1 + 1e-9
                and abs(value / size - count / population) <= 0.02 + 1e-9
                for value in range(min(size, count) + 1)
            )
            for count in counts
        )
    ]
    assert possible == []
    samples = _samples(counts)
    request = SplitRequest(name="unattainable", ratios=SplitRatios(train=0.9, val=0.05, test=0.05))
    members = split_samples(samples, request)
    assert len(members) == population
    for distribution in distributions(members):
        assert all(
            abs(
                label.count - counts[int(label.label)] * getattr(request.ratios, distribution.split)
            )
            <= 1 + 1e-9
            for label in distribution.labels
        )


def test_integer_solver_shifts_small_totals_to_the_nearest_feasible_allocation() -> None:
    """The feasible small-set solution honors prevalence ahead of global ratio proximity."""
    samples = _samples((55, 52, 52))
    initial: dict[int, SplitName] = dict.fromkeys(range(len(samples)), "train")
    result = balance_single_labels(samples, initial, SplitRequest(name="small-quota"))
    assert [
        sum(value == split for value in result.values()) for split in ("train", "val", "test")
    ] == [129, 15, 15]
