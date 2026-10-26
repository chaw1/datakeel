# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build the explicit five-node deterministic evidence extraction preset."""

from typing import Literal

from datakeel.operators.evidence import (
    annotation_labels,
    caption_mentions,
    image_phash,
    label_gap,
    near_duplicate,
)
from datakeel.pipeline.models import Node, Pipeline


def evidence_pipeline(mode: Literal["prefix", "exact"] | None = None) -> Pipeline:
    """Resolve each extractor version independently without changing upstream content."""
    nodes = [Node(id="evidence_images", kind="route", inputs={"files": "$input.files"})]
    source = "evidence_images.image"
    for module in (image_phash, caption_mentions, annotation_labels, label_gap, near_duplicate):
        identifier = module.OPERATOR.manifest.id.removeprefix("evidence.")
        nodes.append(
            Node(
                id=identifier,
                operator=module.OPERATOR.manifest.id,
                inputs={"files": source},
                params={
                    "extractor_version": module.VERSION,
                    **({"mode": mode} if module is near_duplicate and mode is not None else {}),
                },
            )
        )
        source = f"{identifier}.files"
    return Pipeline(nodes=nodes, outputs=[source], max_workers=1)
