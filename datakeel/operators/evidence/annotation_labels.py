# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse COCO subset labels and convert their boxes to source-pixel xyxy anchors."""

import unicodedata
from pathlib import Path

from pydantic import ConfigDict

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import EvidenceValue, ExtractorRef, ImageRegion
from datakeel.core.models import BoundaryModel, FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.evidence.common import EvidenceParams, anchor, publish, subject
from datakeel.operators.evidence.contracts import Lexicon, read_lexicon
from datakeel.operators.evidence.facts import AnnotationBox, AnnotationFacts, ImageDimensions
from datakeel.operators.image.helpers import open_image

VERSION = "1.0"


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


def _dimensions(file: FileItem, document: CocoDocument) -> ImageDimensions:
    if file.metadata.get("image_dimensions"):
        return ImageDimensions.model_validate(file.metadata["image_dimensions"])
    if document.width is not None and document.height is not None:
        return ImageDimensions(width=document.width, height=document.height)
    with open_image(file) as image:
        return ImageDimensions(width=image.width, height=image.height)


def _boxes(file: FileItem, sidecar: FileItem, lexicon: Lexicon) -> list[AnnotationBox]:
    document = CocoDocument.model_validate_json(Path(sidecar.path).read_bytes())
    dimensions = _dimensions(file, document)
    categories = {
        unicodedata.normalize("NFC", name).casefold(): concept.id
        for concept in lexicon.concepts
        for name in concept.annotation_categories
    }
    boxes: list[AnnotationBox] = []
    for annotation in document.annotations:
        concept = categories.get(unicodedata.normalize("NFC", annotation.category).casefold())
        if concept is not None:
            x, y, width, height = annotation.bbox
            region = ImageRegion(bbox=(x, y, x + width, y + height), **dimensions.model_dump())
            boxes.append(
                AnnotationBox(concept=concept, bbox=region.bbox, **dimensions.model_dump())
            )
    return boxes


def _labels(file: FileItem, params: EvidenceParams) -> FileItem:
    owner, sidecar, lexicon = subject(file), sample_sidecars(file).annotation, read_lexicon()
    boxes: list[AnnotationBox] = []
    failed = False
    if sidecar is not None:
        try:
            boxes = _boxes(file, sidecar, lexicon)
        except (OSError, ValueError):
            failed = True
    drafts: list[ObservationDraft] = []
    for concept in (concept for concept in lexicon.concepts if concept.kind == "object"):
        selected = [box for box in boxes if box.concept == concept.id]
        evidence = tuple(
            anchor(file, owner, ImageRegion(bbox=box.bbox, width=box.width, height=box.height))
            for box in selected
        )
        evidence += (anchor(file if failed else sidecar or file, owner),)
        drafts.append(
            ObservationDraft(
                subject=owner,
                predicate="annotated_as",
                object=EvidenceValue(
                    concept=concept.id, value="present" if selected else "unknown"
                ),
                anchors=evidence,
                extractor=ExtractorRef(
                    id="evidence.annotation_labels", version=params.extractor_version
                ),
                confidence=1 if selected else None,
                reason="Explicit annotation"
                if selected
                else "Annotation unavailable or category not observed",
            )
        )
    facts = AnnotationFacts(
        annotation_available=sidecar is not None and not failed,
        annotation_categories=tuple(sorted({box.concept for box in boxes})),
        annotation_boxes=tuple(boxes),
    )
    return publish(file, drafts, failed=failed, **facts.model_dump(mode="json"))


def execute(files: list[FileItem], _output_dir: Path, params: EvidenceParams) -> OperatorResult:
    """Retain explicit boxes and unknown categories without treating non-detection as absence."""
    return summarize(files, [_labels(file, params) for file in files])


OPERATOR = Operator("evidence.annotation_labels", "image", "evidence", EvidenceParams, execute)
