# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Simultaneous marginal quotas for overlapping labels, independent of label tuple strata."""

import math
from collections import Counter

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitMember, SplitRatios, SplitRequest, TrainingSample
from datakeel.training.splitting import distributions, split_samples


def _samples(labels: list[tuple[str, ...]]) -> tuple[TrainingSample, ...]:
    return tuple(
        TrainingSample(
            file=FileItem(
                id=f"item-{index}", path="unused", filename=str(index), sha256=str(index)
            ),
            labels=value,
        )
        for index, value in enumerate(labels)
    )


def _assert_limits(
    samples: tuple[TrainingSample, ...], members: tuple[SplitMember, ...], request: SplitRequest
) -> None:
    totals = Counter(label for sample in samples for label in set(sample.labels))
    for row in distributions(members):
        for category in row.labels:
            target = totals[category.label] * getattr(request.ratios, row.split)
            assert abs(category.count - target) <= 1 + 1e-9
            if totals[category.label] >= 50 and row.count:
                assert (
                    abs(category.count / row.count - totals[category.label] / len(samples))
                    <= 0.02 + 1e-9
                )


@pytest.mark.parametrize("seed", [0, 3, 7, 19, 25, 54, 97, 385])
@pytest.mark.parametrize("ratios", [(0.8, 0.1, 0.1), (0.7, 0.2, 0.1), (0.85, 0.15, 0)])
def test_overlapping_labels_meet_simultaneous_marginal_limits(
    seed: int, ratios: tuple[float, float, float]
) -> None:
    """Every label is checked, including non-primary labels and correlated combinations."""
    generator = np.random.default_rng(seed)
    samples = _samples(
        [tuple(str(label) for label in range(8) if generator.random() < 0.4) for _ in range(300)]
    )
    request = SplitRequest(
        name="all-labels",
        seed=seed,
        ratios=SplitRatios.model_validate(dict(zip(("train", "val", "test"), ratios, strict=True))),
    )
    members = split_samples(samples, request)
    _assert_limits(samples, members, request)
    changed = tuple(
        sample.model_copy(update={"labels": (*reversed(sample.labels), *sample.labels)})
        for sample in reversed(samples)
    )
    assert [(row.sample_id, row.split) for row in members] == [
        (row.sample_id, row.split) for row in split_samples(changed, request)
    ]
    assert len({row.sample_id for row in members}) == len(samples)


@pytest.mark.parametrize("seed", [0, 19, 22, 23, 28, 34, 91, 97])
def test_nonuniform_sparse_multilabel_prevalence_is_balanced(seed: int) -> None:
    """Sparse and strongly unequal marginal frequencies retain the two percentage-point bound."""
    generator = np.random.default_rng(seed)
    population = (300, 500, 1000)[seed % 3]
    labels: list[list[str]] = [[] for _ in range(population)]
    for category, count in enumerate(generator.integers(50, int(population * 0.85), size=6)):
        for index in generator.choice(population, size=int(count), replace=False):
            labels[int(index)].append(str(category))
    samples = _samples([tuple(row) for row in labels])
    request = SplitRequest(
        name="sparse",
        seed=seed,
        ratios=SplitRatios(train=0.8, val=0.1, test=0.1)
        if seed == 0
        else SplitRatios(train=0.9, val=0.05, test=0.05),
    )
    _assert_limits(samples, split_samples(samples, request), request)


def test_correlated_rare_labels_and_atomic_duplicate_groups_keep_all_quotas() -> None:
    """A feasible grouped fixture checks rare labels, cooccurrences and group isolation together."""
    patterns = [("a", "b"), ("a", "c"), ("b",), ("c",), ("rare",), ()]
    samples = tuple(
        sample.model_copy(update={"group": str(index // 2)})
        for index, sample in enumerate(_samples([row for row in patterns for _ in range(100)]))
    )
    request = SplitRequest(name="groups", seed=14)
    members = split_samples(samples, request)
    _assert_limits(samples, members, request)
    assignment = {row.sample_id: row.split for row in members}
    assert all(
        assignment[f"item-{index}"] == assignment[f"item-{index + 1}"]
        for index in range(0, len(samples), 2)
    )


def test_small_multilabel_integer_limits_can_be_mathematically_unattainable() -> None:
    """No partition size permits all six per-label quotas and prevalence intervals here."""
    totals = (224, 180, 154, 105, 113, 58)
    population = 300
    allowed_sizes = [
        size
        for size in range(population + 1)
        if all(
            max(
                math.ceil(total * 0.05 - 1 - 1e-9),
                math.ceil((total / population - 0.02) * size - 1e-9),
            )
            <= min(
                math.floor(total * 0.05 + 1 + 1e-9),
                math.floor((total / population + 0.02) * size + 1e-9),
            )
            for total in totals
        )
    ]
    assert allowed_sizes == []


@pytest.mark.parametrize("seed", [3, 5, 17])
def test_rare_secondary_labels_keep_quotas_beside_correlated_common_labels(seed: int) -> None:
    """Small rare strata retain their count budget even without a prevalence requirement."""
    samples = _samples(
        [
            tuple(
                label
                for label, included in (
                    ("a", index < 150),
                    ("b", index % 3 != 0),
                    ("rare-seven", index < 7),
                    ("rare-thirteen", 20 <= index < 33),
                )
                if included
            )
            for index in range(300)
        ]
    )
    request = SplitRequest(name="rare", seed=seed)
    _assert_limits(samples, split_samples(samples, request), request)
