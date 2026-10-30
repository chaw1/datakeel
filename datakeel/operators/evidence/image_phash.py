# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure a deterministic 64-bit dHash and explicit image decoding state."""

from pathlib import Path

import numpy as np
from PIL import Image

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceValue, ExtractorRef
from datakeel.core.image_orientation import ORIENTATION_TAG, ImageGeometry, orientation_value
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.evidence.common import EvidenceParams, anchor, publish, subject
from datakeel.operators.evidence.contracts import read_near_duplicate
from datakeel.operators.evidence.facts import ImageDimensions
from datakeel.operators.image.helpers import open_image

# 1.1: image_dimensions became the upright (EXIF-applied) size; 1.0 cache entries are stale.
VERSION = "1.1"


def dhash(image: Image.Image) -> str:
    """Encode right-greater-than-left grayscale comparisons in row-major bit order."""
    settings = read_near_duplicate()
    pixels = np.asarray(
        image.convert("L").resize((settings.width, settings.height), Image.Resampling.LANCZOS)
    )
    bits = (pixels[:, 1:] > pixels[:, :-1]).flat
    value = int("".join("1" if bit else "0" for bit in bits), 2)
    return f"{value:016x}"


def _upright_size(image: Image.Image) -> ImageDimensions:
    """Report the EXIF-applied size, the frame every displayed box uses."""
    geometry = ImageGeometry(
        orientation=orientation_value(image.getexif().get(ORIENTATION_TAG)),
        stored_width=image.width,
        stored_height=image.height,
    )
    return ImageDimensions(width=geometry.width, height=geometry.height)


def _measure(file: FileItem, params: EvidenceParams) -> FileItem:
    owner = subject(file)
    try:
        with open_image(file) as image:
            perceptual_hash = dhash(image)
            dimensions = _upright_size(image)
    except (OSError, ValueError, Image.DecompressionBombError):
        perceptual_hash, dimensions = None, None
    failed = perceptual_hash is None
    draft = ObservationDraft(
        subject=owner,
        predicate="corrupt",
        object=EvidenceValue(value="present" if failed else "absent"),
        anchors=(anchor(file, owner),),
        extractor=ExtractorRef(id="evidence.image_phash", version=params.extractor_version),
        confidence=1,
        reason="Image decode failed" if failed else "Image decoded successfully",
    )
    return publish(
        file,
        [draft],
        failed=failed,
        image_phash=perceptual_hash,
        image_dimensions=dimensions.model_dump(mode="json") if dimensions else None,
    )


def execute(files: list[FileItem], _output_dir: Path, params: EvidenceParams) -> OperatorResult:
    """Keep every source sample, including corrupt inputs with a Whole evidence anchor."""
    return summarize(files, [_measure(file, params) for file in files])


OPERATOR = Operator("evidence.image_phash", "image", "evidence", EvidenceParams, execute)
