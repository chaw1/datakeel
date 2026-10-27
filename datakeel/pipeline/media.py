# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A complete local media cleaning DAG retaining measured originals and derived clips."""

from typing import Any

from datakeel.pipeline.models import Node, Pipeline

# Measured originals are published next to clips cut from their clean ranges;
# normalization keeps the timeline, so the measured issue intervals still apply.
_CHAINS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "video": [
        ("probe", {}),
        ("invalid_frames", {}),
        ("dedup", {"window_ms": 1000}),
        ("normalize", {"width": 160, "height": 120, "frame_rate": 30.0}),
        ("segment", {"window_ms": 2000, "skip_issues": True}),
        ("invalid_frames", {"remove": True}),
    ],
    "audio": [
        ("probe", {}),
        ("vad", {}),
        ("clipping", {}),
        ("loudness", {}),
        ("dedup", {"remove": False}),
        ("trim_silence", {}),
        ("vad", {}),
        ("clipping", {}),
        ("loudness", {}),
    ],
}
# Unique audio continues from a removing deduplication node; the annotated one is kept.
_AUDIO_UNIQUE_BEFORE = "trim_silence"


def media_pipeline(*, align: bool = False) -> Pipeline:
    """Probe, inspect, deduplicate, segment clean ranges and normalize recordings."""
    nodes = [
        Node(
            id="modality",
            kind="route",
            inputs={"files": "align.files" if align else "$input.files"},
        )
    ]
    if align:
        nodes.insert(0, Node(id="align", operator="media.align", inputs={"files": "$input.files"}))
    nodes.append(
        Node(
            id="audio_unique",
            operator="audio.dedup",
            inputs={"files": "audio_3.files"},
            params={"remove": True},
        )
    )
    for modality, operations in _CHAINS.items():
        source = f"modality.{modality}"
        for index, (operation, params) in enumerate(operations):
            identifier = f"{modality}_{index}"
            if modality == "audio" and operation == _AUDIO_UNIQUE_BEFORE:
                source = "audio_unique.files"
            nodes.append(
                Node(
                    id=identifier,
                    operator=f"{modality}.{operation}",
                    inputs={"files": source},
                    params=params,
                )
            )
            source = f"{identifier}.files"
    return Pipeline(
        nodes=nodes,
        outputs=["video_2.files", "video_5.files", "audio_4.files", "audio_8.files"],
        max_workers=2,
    )
