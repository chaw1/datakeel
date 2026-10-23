# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate reusable observations serialized between deterministic DAG operators."""

from pydantic import Field

from datakeel.core.models import BoundaryModel, FileItem


class ImageDimensions(BoundaryModel):
    """Describe the decoded original image coordinate space."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)


class AnnotationBox(ImageDimensions):
    """Persist normalized concept labels and original-image xyxy boxes."""

    concept: str
    bbox: tuple[float, float, float, float]


class CaptionFacts(BoundaryModel):
    """Separate missing caption data from an available caption without a match."""

    caption_available: bool = False
    caption_text: str | None = None
    caption_mentions: tuple[str, ...] = ()


class AnnotationFacts(BoundaryModel):
    """Separate missing annotations from a known empty annotation collection."""

    annotation_available: bool = False
    annotation_categories: tuple[str, ...] = ()
    annotation_boxes: tuple[AnnotationBox, ...] = ()


def caption_facts(file: FileItem) -> CaptionFacts:
    """Validate only caption-owned metadata without admitting unrelated properties."""
    return CaptionFacts.model_validate(
        {name: file.metadata[name] for name in CaptionFacts.model_fields if name in file.metadata}
    )


def annotation_facts(file: FileItem) -> AnnotationFacts:
    """Validate only annotation-owned metadata without admitting unrelated properties."""
    return AnnotationFacts.model_validate(
        {
            name: file.metadata[name]
            for name in AnnotationFacts.model_fields
            if name in file.metadata
        }
    )
