# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image quality and point-cloud inspection/cleanup presets."""

from datakeel.pipeline.models import Node, Pipeline


def media_pipeline(*, clean: bool = False, sensor: str | None = None) -> Pipeline:
    """Measure originals or clean point clouds while preserving source observations.

    ``sensor`` declares the capture form of the point clouds, which selects
    plausible extents and the sparse-coverage limit; undeclared clouds only
    receive sparse hints.
    """
    nodes = [
        Node(id="modality", kind="route", inputs={"files": "$input.files"}),
        Node(id="image_quality", operator="image.quality", inputs={"files": "modality.image"}),
    ]
    source = "modality.pointcloud"
    operators = ["probe", "unit_check"]
    if clean:
        operators.extend(["clean", "downsample", "outliers"])
    operators.append("preview")
    for name in operators:
        identifier = f"pointcloud_{name}"
        params = {"sensor": sensor} if name == "probe" and sensor is not None else {}
        nodes.append(
            Node(
                id=identifier,
                operator=f"pointcloud.{name}",
                inputs={"files": source},
                params=params,
            )
        )
        source = f"{identifier}.files"
    return Pipeline(
        nodes=nodes,
        outputs=["image_quality.files", source, "modality.text", "modality.other"],
    )
