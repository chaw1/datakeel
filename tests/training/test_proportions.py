# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Count and prevalence constraints across uneven labels and small integer partitions."""

from collections import Counter

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitMember, SplitRatios, SplitRequest, TrainingSample
from datakeel.training.splitting import distributions, split_samples


def _samples(labels: list[tuple[str, ...]]) -> tuple[TrainingSample, ...]:
    return tuple(
        TrainingSample(
            file=FileItem(id=str(index), filename=str(index), path="unused", sha256=str(index)),
            labels=value,
        )
        for index, value in enumerate(labels)
    )


def _assert_limits(
    samples: tuple[TrainingSample, ...], members: tuple[SplitMember, ...], request: SplitRequest
) -> None:
    totals = Counter(label for sample in samples for label in sample.labels)
    for distribution in distributions(members):
        for label in distribution.labels:
            raw = totals[label.label] * getattr(request.ratios, distribution.split)
            assert abs(label.count - raw) <= 1 + 1e-9
            if totals[label.label] >= 50 and distribution.count:
                assert (
                    abs(label.count / distribution.count - totals[label.label] / len(samples))
                    <= 0.02 + 1e-9
                )


def test_small_single_label_sets_shift_totals_to_preserve_class_prevalence() -> None:
    """A feasible 129/15/15 allocation beats the 2.909pp error at rigid set totals."""
    samples = _samples(
        [(label,) for label, count in (("a", 55), ("b", 52), ("c", 52)) for _ in range(count)]
    )
    request = SplitRequest(name="small", seed=7)
    members = split_samples(samples, request)
    _assert_limits(samples, members, request)
    assert [row.count for row in distributions(members)] == [129, 15, 15]
    assert members == split_samples(tuple(reversed(samples)), request)


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize(
    "ratios", [(0.8, 0.1, 0.1), (0.7, 0.2, 0.1), (0.5, 0.25, 0.25), (0.85, 0.15, 0)]
)
def test_uneven_single_label_counts_near_fifty_meet_both_limits(
    seed: int, ratios: tuple[float, float, float]
) -> None:
    """Integer rounding is checked across unequal strata and two/three-set policies."""
    generator = np.random.default_rng(seed)
    counts = generator.integers(50, 101, size=int(generator.integers(3, 9)))
    samples = _samples(
        [(str(label),) for label, count in enumerate(counts) for _ in range(int(count))]
    )
    request = SplitRequest(
        name="uneven", seed=seed, ratios=SplitRatios(train=ratios[0], val=ratios[1], test=ratios[2])
    )
    _assert_limits(samples, split_samples(samples, request), request)


def test_prevalence_balancing_never_breaks_atomic_groups() -> None:
    """Whole-group transfers retain complete cohorts when numeric limits are unattainable."""
    samples = tuple(
        sample.model_copy(update={"group": str(index // 5)})
        for index, sample in enumerate(_samples([("a",)] * 55 + [("b",)] * 52 + [("c",)] * 52))
    )
    members = split_samples(samples, SplitRequest(name="atomic"))
    assigned = {member.sample_id: member.split for member in members}
    for offset in range(0, len(samples), 5):
        assert (
            len({assigned[str(index)] for index in range(offset, min(offset + 5, len(samples)))})
            == 1
        )
