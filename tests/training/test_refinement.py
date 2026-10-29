# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""All-label allocation preserves indivisible groups with overlapping source labels."""

import numpy as np

from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRequest, TrainingSample
from datakeel.training.splitting import split_samples


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
