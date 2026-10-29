# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed sidecars and independent ground truth for the evidence benchmark."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel

Split = Literal["train", "val", "test"]
Transformation = Literal["crop", "resize", "noise", "controlled_chain"]


class Annotation(BoundaryModel):
    """Describe a synthetic object using COCO pixel coordinates (x, y, w, h)."""

    category: str
    bbox: tuple[int, int, int, int]


class AnnotationSidecar(BoundaryModel):
    """Persist the image size and explicitly supplied annotation collection."""

    schema_version: str = "1.0"
    width: int = 192
    height: int = 128
    annotations: list[Annotation] = Field(default_factory=list[Annotation])


class GoldSample(BoundaryModel):
    """Record independent expected facts; extraction must never read this model."""

    sample_id: str
    image: str
    caption_path: str
    annotation_path: str | None
    split: Split
    caption: str
    concepts: list[str]
    annotation_categories: list[str]
    scenes: dict[str, Literal["present", "unknown"]]
    label_gaps: list[str]
    corrupt: bool
    missing_annotation: bool
    dark_scene: bool


class NearDuplicatePair(BoundaryModel):
    """Identify one injected pair by paths relative to the generated directory."""

    left: str
    right: str
    transformation: Transformation


class NonTransitiveChain(BoundaryModel):
    """Record a measured A-B-C chain whose endpoints must remain unrelated."""

    a: str
    b: str
    c: str
    distance_ab: int = 6
    distance_bc: int = 6
    distance_ac: int = 12
    threshold: int = 8


class SampleGold(BoundaryModel):
    """Provide the complete evaluation denominator without generated timestamps."""

    schema_version: str = "1.0"
    seed: int = 17
    sample_count: int
    train_count: int
    val_count: int
    samples: list[GoldSample]
    near_duplicate_pairs: list[NearDuplicatePair]
    non_transitive_chains: list[NonTransitiveChain] = Field(
        default_factory=list[NonTransitiveChain]
    )
