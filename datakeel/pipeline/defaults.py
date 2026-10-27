# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical reproducible demonstration pipeline."""

from pydantic import JsonValue

from datakeel.pipeline.models import Pipeline


def default_pipeline() -> Pipeline:
    """Return the canonical thirteen-node image/text demonstration DAG."""
    nodes: list[dict[str, JsonValue]] = []

    def add(identifier: str, operator: str, source: str, **params: JsonValue) -> None:
        nodes.append(
            {"id": identifier, "operator": operator, "inputs": {"files": source}, "params": params}
        )

    add("dedup", "file.dedup", "$input.files")
    add("corrupt", "file.corrupt_check", "dedup.files")
    add("empty", "file.empty_check", "corrupt.files")
    nodes.append(
        {
            "id": "nonempty",
            "kind": "condition",
            "inputs": {"files": "empty.files"},
            "params": {"min_count": 1},
        }
    )
    nodes.append({"id": "modality", "kind": "route", "inputs": {"files": "nonempty.true"}})
    add("image_quality", "image.quality", "modality.image")
    add("resize", "image.resize", "image_quality.files", width=512, height=512)
    add("thumbnail", "image.thumbnail", "resize.files", size=128)
    add("convert", "image.convert", "thumbnail.files", format="png")
    add("encoding", "text.encoding_fix", "modality.text")
    add("redact", "text.pii_redact", "encoding.files")
    add("text_dedup", "text.dedup", "redact.files")
    add("text_quality", "text.quality", "text_dedup.files")
    return Pipeline.model_validate(
        {
            "nodes": nodes,
            "outputs": [
                "convert.files",
                "text_quality.files",
                "modality.pointcloud",
                "modality.other",
                "nonempty.false",
            ],
            "max_workers": 4,
        }
    )
