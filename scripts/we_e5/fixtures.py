# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic synthetic content and independent explicit-vector fixtures only."""

import random

from datakeel.core.models import BoundaryModel
from scripts.we_e5.models import NumericInput, Point, Workload


class Content(BoundaryModel):
    """Generated text metadata declares contract gold without reading any external corpus."""

    asset_id: str
    text: str
    group: str
    cluster: int


def contents(workload: Workload) -> tuple[Content, ...]:
    """Repeat authored groups exactly, then add independently declared singleton noise."""
    generator = random.Random(workload.seed)  # noqa: S311  # Reproducible public fixtures, no secrets.
    groups = (workload.assets - workload.noise_assets) // workload.duplicate_group_size
    texts = [f"Synthetic E5 group {i}: {generator.getrandbits(64):016x}." for i in range(groups)]
    output: list[Content] = []
    for index in range(workload.assets):
        group = index // workload.duplicate_group_size
        clustered = index < groups * workload.duplicate_group_size
        output.append(
            Content(
                asset_id=f"target-{index:05d}",
                text=texts[group]
                if clustered
                else f"Synthetic noise {index}: {generator.getrandbits(64):016x}.",
                group=f"group-{group}" if clustered else f"singleton-{index}",
                cluster=group if clustered else -1,
            )
        )
    return tuple(output)


def references(workload: Workload) -> tuple[Content, ...]:
    """Freeze external R as one separate asset from each of the first declared groups."""
    targets = contents(workload)
    return tuple(
        targets[i * workload.duplicate_group_size].model_copy(update={"asset_id": f"ref-{i:05d}"})
        for i in range(workload.reference_groups)
    )


def explicit_case() -> NumericInput:
    """Use handwritten orthogonal/sign/scaled axes with known duplicate, cluster and gap gold."""
    return NumericInput(
        points=tuple(
            Point(asset_id=k, values=v)
            for k, v in (
                ("a", (3.0, 0.0)),
                ("b", (7.0, 0.0)),
                ("c", (0.0, 5.0)),
                ("d", (0.0, 8.0)),
                ("z", (-2.0, 0.0)),
            )
        ),
        targets=("a", "b", "c", "d", "z"),
        references=("a", "b"),
        prefix=2,
        threshold=1.0,
        eps=0.0,
        min_samples=2,
        gap_threshold=0.5,
        duplicate_gold=("x", "x", "y", "y", "z"),
        cluster_gold=(0, 0, 1, 1, -1),
        gap_gold=("c", "d", "z"),
    )
