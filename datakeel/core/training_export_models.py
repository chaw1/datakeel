# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed portable training formats and version-bound export inputs."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import BoundaryModel, FileItem

TrainingFormat = Literal["coco", "yolo", "imagefolder", "hf_imagefolder", "text_jsonl"]
TRAINING_FORMATS = frozenset({"coco", "yolo", "imagefolder", "hf_imagefolder", "text_jsonl"})
TRAINING_ARCHIVE_SUFFIXES = (".tar", ".tar.gz", ".tgz")


class TrainingExportItem(BoundaryModel):
    """Pair a source version file with its frozen annotation and split membership."""

    file: FileItem
    split: Literal["train", "val", "test"]
    annotation: AnnotationRecord


class TrainingExport(BoundaryModel):
    """Bind an archive to one immutable version, split and annotation selection."""

    dataset_id: str
    version_id: str
    release_id: str | None = None
    split_set_id: str
    seed: int
    format: TrainingFormat
    items: tuple[TrainingExportItem, ...]


class HfImageMetadata(BoundaryModel):
    """Keep every split's inferred metadata schema stable, including unreviewed/empty labels.

    JSON text columns preserve nullable variable-length annotations without Arrow inferring
    incompatible list element types in splits containing only negative images.
    """

    file_name: str
    sample_id: str
    annotator_id: str
    width: int
    height: int
    labels_json: str
    boxes_json: str


class CocoCategory(BoundaryModel):
    """Describe a standard COCO detection category."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    id: int
    name: str = Field(min_length=1)
    supercategory: str = ""


class CocoImage(BoundaryModel):
    """Describe an image in a standard COCO detection document."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    id: int
    file_name: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    datakeel_sample_id: str | None = None


class CocoBox(BoundaryModel):
    """Store standard absolute xywh coordinates with explicit image/category identities."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    id: int
    image_id: int
    category_id: int
    bbox: tuple[float, float, float, float]
    area: float | None = None
    iscrowd: Literal[0, 1] = 0


class CocoDataset(BoundaryModel):
    """Accept standard detection COCO while ignoring unrelated upstream extensions."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    images: tuple[CocoImage, ...]
    annotations: tuple[CocoBox, ...]
    categories: tuple[CocoCategory, ...]


class YoloImage(BoundaryModel):
    """Carry normalized YOLO text together with the dimensions needed to restore pixels."""

    sample_id: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    labels: str


class YoloDataset(BoundaryModel):
    """Provide zero-indexed category names and one label text per source image."""

    names: tuple[Annotated[str, Field(min_length=1)], ...]
    images: tuple[YoloImage, ...]


class TrainingAnnotationImport(BoundaryModel):
    """Import COCO or YOLO detections into the existing immutable annotation history."""

    format: Literal["coco", "yolo"]
    name: str = Field(default="Training annotations", min_length=1, max_length=200)
    annotator_id: str = Field(default="training", min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    coco: CocoDataset | None = None
    yolo: YoloDataset | None = None
    sample_ids: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def matching_format(self) -> "TrainingAnnotationImport":
        """Reject ambiguous documents instead of silently ignoring an extra payload."""
        if (self.coco is not None) != (self.format == "coco") or (self.yolo is not None) != (
            self.format == "yolo"
        ):
            message = "Supply exactly the document matching the selected import format"
            raise ValueError(message)
        return self
