# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deal the mutation catalog into CI shards whose union is the whole catalog."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.mutation_models import Mutation
    from scripts.shard_spec import ShardSpec


def select_mutations(mutations: Sequence[Mutation], shard: ShardSpec) -> tuple[Mutation, ...]:
    """Deal golden and pytest mutations round-robin separately, keeping catalog order.

    Golden mutations each run a complete evaluation, so dealing each runner kind on its own
    keeps the expensive evaluations evenly spread over shards.
    """
    positions: Counter[str] = Counter()
    selected: list[Mutation] = []
    for mutation in mutations:
        position = positions[mutation.runner]
        positions[mutation.runner] += 1
        if position % shard.count == shard.index - 1:
            selected.append(mutation)
    return tuple(selected)
