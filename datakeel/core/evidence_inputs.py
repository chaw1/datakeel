# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable sidecar references carried by a paired image manifest."""

from typing import Literal

from pydantic import ConfigDict, Field

from datakeel.core.models import BoundaryModel, FileItem

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


class CocoAnnotation(BoundaryModel):
    """Accept the supported category/bbox subset of a larger COCO annotation."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    category: str
    bbox: tuple[float, float, float, float]


class CocoDocument(BoundaryModel):
    """Ignore unrelated COCO properties while validating supplied annotations."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    annotations: tuple[CocoAnnotation, ...]
    width: int | None = None
    height: int | None = None


class SampleSidecars(BoundaryModel):
    """Bind independently persisted sidecar bytes without consulting evaluation gold."""

    sample_key: str = Field(min_length=1)
    split: Literal["train", "val", "test"]
    caption: FileItem | None = None
    annotation: FileItem | None = None


def sample_sidecars(file: FileItem) -> SampleSidecars:
    """Validate the complete sidecar boundary stored in one image's metadata."""
    return SampleSidecars.model_validate(file.metadata.get("evidence_sample"))
