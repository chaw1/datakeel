# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate image labels, file boundaries and byte-level provenance before evaluation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_models import ImageRegion
from datakeel.core.kg_image_eval import KGImageSuite
from datakeel.kg.loader import contracts_path, load_contract
from datakeel.kg_eval.loader import validate_case
from datakeel.transcription.images import normalize_image

if TYPE_CHECKING:
    from datakeel.core.kg_contracts import KGSchema


def image_path(directory: Path, relative: str) -> Path:
    """Reject absolute paths and symlink traversal outside the selected case directory."""
    path = (directory / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(directory.resolve()):
        msg = "Image case path must stay inside its case directory"
        raise ValidationError(msg)
    return path


def load_image_cases(
    schema: KGSchema, directory: Path | None = None
) -> tuple[KGImageSuite, str, Path]:
    """Load frozen gold labels and hash all image bytes, including external holdout suites."""
    directory = directory or contracts_path() / "eval" / "image"
    path = directory / "cases.yaml"
    suite = load_contract(path, KGImageSuite)
    if len({case.id for case in suite.cases}) != len(suite.cases):
        msg = "cases.yaml:cases.id: duplicate case identity"
        raise ValidationError(msg)
    digest = hashlib.sha256(path.read_bytes())
    for index, case in enumerate(suite.cases):
        validate_case(case, schema, f"cases.yaml:cases.{index}")
        try:
            content = image_path(directory, case.image).read_bytes()
        except OSError as error:
            msg = "Image case file is unavailable"
            raise ValidationError(msg) from error
        if case.image_hash and hashlib.sha256(content).hexdigest() != case.image_hash:
            msg = "Image case content differs from its recorded hash"
            raise ValidationError(msg)
        image = normalize_image(content)
        try:
            for relation in case.relations:
                for box in relation.boxes:
                    ImageRegion(bbox=box, width=image.width, height=image.height)
        except ModelValidationError as error:
            msg = "Image gold box lies outside corrected image pixels"
            raise ValidationError(msg) from error
        digest.update(content)
    return suite, digest.hexdigest(), directory
