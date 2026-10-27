# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed operator contracts and immutable artifact helpers."""

import hashlib
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, JsonValue, model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem, Record
from datakeel.operators.image.limits import validate_dimensions


class Params(Record):
    """Reject undeclared parameters before an operator runs."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class EmptyParams(Params):
    """Declare an operator with no configurable parameters."""


class FilterParams(Params):
    """Control whether invalid files are removed from outputs."""

    remove: bool = True


class ResizeParams(Params):
    """Bound the requested output image dimensions."""

    width: int = Field(default=512, ge=1, le=16384)
    height: int = Field(default=512, ge=1, le=16384)
    preserve_aspect: bool = True

    @model_validator(mode="after")
    def bounds(self) -> "ResizeParams":
        """Validate cross-field parameter constraints."""
        validate_dimensions(self.width, self.height)
        return self


class ThumbnailParams(Params):
    """Bound the longest side of generated thumbnails."""

    size: int = Field(default=128, ge=1, le=2048)


class ConvertParams(Params):
    """Select a supported image encoding and its quality."""

    format: Literal["png", "jpg", "webp"] = "png"
    quality: int = Field(default=90, ge=1, le=100)


class ImageQualityParams(Params):
    """Define image-quality thresholds in luminance, pixels and robust noise sigma."""

    blur_threshold: float = Field(default=50.0, ge=0)
    min_brightness: float = Field(default=20.0, ge=0, le=255)
    max_brightness: float = Field(default=235.0, ge=0, le=255)
    min_resolution: int = Field(default=64, ge=1)
    max_noise_sigma: float = Field(default=12.0, gt=0, le=255)
    min_color_stddev: float = Field(default=5.0, gt=0, le=128)
    max_clipped_fraction: float = Field(default=0.5, ge=0, le=1)
    analysis_size: int = Field(default=512, ge=32, le=2048)

    @model_validator(mode="after")
    def bounds(self) -> "ImageQualityParams":
        """Validate cross-field parameter constraints."""
        if self.min_brightness > self.max_brightness:
            msg = "min_brightness must not exceed max_brightness"
            raise ValidationError(msg)
        return self


class EncodingParams(Params):
    """Select the fallback for non-UTF-8 text."""

    fallback: Literal["cp1252", "latin-1", "gb18030"] = "cp1252"


class PiiParams(Params):
    """Configure deterministic contact-information redaction."""

    emails: bool = True
    phones: bool = True
    replacement: str = Field(default="[REDACTED]", min_length=1, max_length=100)


class TextDedupParams(Params):
    """Configure exact or similarity-based text deduplication."""

    approximate: bool = True
    threshold: float = Field(default=0.9, ge=0, le=1)


class TextQualityParams(Params):
    """Define minimum text content and printable-character ratio."""

    min_characters: int = Field(default=20, ge=0)
    min_printable_ratio: float = Field(default=0.95, ge=0, le=1)


class OperatorManifest(Record):
    """Describe typed input/output slots and JSON parameter schemas."""

    id: str
    modality: str
    category: str
    inputs: dict[str, str]
    outputs: dict[str, str]
    parameters: dict[str, Any]
    queue: Literal["cpu", "io", "gpu"] = "cpu"


class OperatorResult(Record):
    """Carry output artifacts and extensible quality measurements."""

    files: list[FileItem]
    quality: dict[str, Any] = Field(default_factory=dict)


class Operator:
    """Bind one manifest to a validated local execution function."""

    def __init__(
        self,
        identifier: str,
        modality: str,
        category: str,
        params: type[Params],
        execute: Callable[[list[FileItem], Path, Any], OperatorResult],
        queue: Literal["cpu", "io", "gpu"] = "cpu",
    ) -> None:
        """Register a bounded operator and derive its public parameter schema."""
        self.params_type = params
        self.execute = execute
        slot = f"files.{modality}"
        self.manifest = OperatorManifest(
            id=identifier,
            modality=modality,
            category=category,
            inputs={"files": slot},
            outputs={"files": slot},
            parameters=params.model_json_schema(),
            queue=queue,
        )

    def run(
        self, files: list[FileItem], output_dir: Path, params: dict[str, Any] | None = None
    ) -> OperatorResult:
        """Validate parameters and execute the declared typed operator."""
        validated = self.params_type.model_validate(params or {})
        if self.manifest.modality != "any" and any(
            file.modality != self.manifest.modality for file in files
        ):
            msg = f"{self.manifest.id} requires {self.manifest.modality} files"
            raise ValidationError(msg)
        output_dir.mkdir(parents=True, exist_ok=True)
        return self.execute(files, output_dir, validated)


def annotate(file: FileItem, **metadata: JsonValue) -> FileItem:
    """Return a copied file with updated metadata."""
    return file.model_copy(update={"metadata": {**file.metadata, **metadata}}, deep=True)


def artifact(
    file: FileItem, output_dir: Path, content: bytes, extension: str, **metadata: JsonValue
) -> FileItem:
    """Materialize immutable output bytes and refreshed content metadata."""
    identifier = str(uuid4())
    filename = Path(file.filename).stem + "." + extension
    path = output_dir / f"{identifier}.{extension}"
    path.write_bytes(content)
    inherited = deepcopy(file.metadata)
    for key in ("image_quality", "text_quality", "width", "height"):
        inherited.pop(key, None)
    empty = not content or (file.modality == "text" and not content.decode("utf-8").strip())
    return FileItem(
        id=identifier,
        path=str(path.resolve()),
        filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        modality=file.modality,
        metadata={
            **inherited,
            "source_file_id": file.id,
            "format": extension,
            "empty": empty,
            "corrupt": False,
            **metadata,
        },
    )


def summarize(
    files: list[FileItem], output: list[FileItem], issues: list[dict[str, Any]] | None = None
) -> OperatorResult:
    """Summarize retained files and measured quality issues."""
    return OperatorResult(
        files=output,
        quality={
            "input_count": len(files),
            "output_count": len(output),
            "removed_count": len(files) - len(output),
            "issues": issues or [],
        },
    )
