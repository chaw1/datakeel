# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Random overlapping label regression cases independent of the iterative heuristic."""

from collections import Counter

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRequest, TrainingSample
from datakeel.training.splitting import distributions, split_samples


@pytest.mark.parametrize("seed", [*range(12), 25, 54, 385])
def test_random_multilabel_overlap_keeps_capacity_and_category_ratios(seed: int) -> None:
    """Nonuniform overlapping labels satisfy both count and prevalence error budgets."""
    generator = np.random.default_rng(seed)
    samples = tuple(
        TrainingSample(
            file=FileItem(id=str(index), path="unused", filename=str(index), sha256=str(index)),
            labels=tuple(str(label) for label in range(8) if generator.random() < 0.4),
        )
        for index in range(300)
    )
    request = SplitRequest(name="overlap", seed=seed)
    members = split_samples(samples, request)
    totals = Counter(label for sample in samples for label in sample.labels)
    result = distributions(members)
    assert [distribution.count for distribution in result] == [240, 30, 30]
    for distribution in result:
        for label in distribution.labels:
            assert (
                abs(label.count - totals[label.label] * getattr(request.ratios, distribution.split))
                <= 1
            )
            assert (
                abs(label.count / distribution.count - totals[label.label] / len(samples))
                <= 0.02 + 1e-9
            )
    assert members == split_samples(tuple(reversed(samples)), request)


def test_refinement_keeps_random_multilabel_group_components_indivisible() -> None:
    """Balancing can swap complete groups while preserving every group membership."""
    generator = np.random.default_rng(91)
    samples = tuple(
        TrainingSample(
            file=FileItem(id=str(index), path="unused", filename=str(index), sha256=str(index)),
            labels=tuple(str(label) for label in range(5) if generator.random() < 0.6),
            group=str(index // 3),
        )
        for index in range(300)
    )
    members = split_samples(samples, SplitRequest(name="grouped"))
    assignment = {member.sample_id: member.split for member in members}
    assert all(
        len({assignment[str(index + offset)] for offset in range(3)}) == 1
        for index in range(0, 300, 3)
    )


def test_unsatisfiable_label_ratios_preserve_one_indivisible_group() -> None:
    """A whole cohort in one group cannot be split solely to improve label proportions."""
    samples = tuple(
        TrainingSample(
            file=FileItem(id=str(index), path="unused", filename=str(index), sha256=str(index)),
            labels=("a", "b"),
            group="all",
        )
        for index in range(12)
    )
    members = split_samples(samples, SplitRequest(name="indivisible"))
    assert len({member.split for member in members}) == 1
