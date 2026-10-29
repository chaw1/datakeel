# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Global operator constraints that preserve complete cross-sample evaluation."""

from datakeel.core.errors import ValidationError
from datakeel.pipeline.models import Pipeline


def validate_shards(pipeline: Pipeline | None, shards: int) -> None:
    """Require a single complete input set for pairwise near-duplicate extraction."""
    if (
        pipeline is not None
        and shards != 1
        and any(
            node.operator
            in {"evidence.near_duplicate", "media.align", "audio.dedup", "video.dedup"}
            for node in pipeline.nodes
        )
    ):
        msg = "Pairwise media/evidence operators require exactly one shard for global recall"
        raise ValidationError(msg)
