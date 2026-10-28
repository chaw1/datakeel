# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen configuration, image inputs and portable image transcription recordings."""

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, JsonValue, field_validator, model_validator

from datakeel.core.evidence_models import ContentRevision, ImageRegion
from datakeel.core.model_parameters import request_parameter_valid
from datakeel.core.models import BoundaryModel

TranscriptionMode = Literal["ocr", "vlm"]
TranscriptionBackend = Literal["ocr", "vlm", "replay", "fake"]
TranscriptionIssue = Literal[
    "empty",
    "truncated",
    "repeated",
    "timeout",
    "provider_error",
    "provider_quota_exhausted",
    "recording_missing",
    "ocr_not_installed",
    "api_key_missing",
    "mode_mismatch",
    "image_decode_error",
]


class TranscriptionProfile(BoundaryModel):
    """Select a backend without embedding credentials or unrestricted request options."""

    id: str = Field(min_length=1)
    backend: TranscriptionBackend
    mode: TranscriptionMode = "ocr"
    model: str = Field(min_length=1)
    interface: Literal["openai", "ollama"] = "openai"
    base_url: str | None = None
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    prompt_version: Literal["image-transcription-v1"] = "image-transcription-v1"
    max_output_tokens: int = Field(default=4096, gt=0)
    timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    request_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    recording: str | None = None
    ocr_model_version: str = Field(default="rapidocr-3.10.0-defaults", min_length=1)

    @field_validator("request_parameters")
    @classmethod
    def validate_parameters(cls, values: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Permit only typed thinking and context controls, never transport overrides."""
        for name, value in values.items():
            if not request_parameter_valid(name, value):
                message = "request_parameters: unsupported parameter name or value"
                raise ValueError(message)
        return values

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Reject unsupported routing and endpoints containing secrets."""
        if self.backend == "ocr" and self.mode != "ocr":
            message = "ocr backend supports only ocr mode"
            raise ValueError(message)
        if self.backend == "vlm" and not self.base_url:
            message = "vlm backend requires an explicit base_url"
            raise ValueError(message)
        if self.backend == "replay" and not self.recording:
            message = "replay backend requires a recording"
            raise ValueError(message)
        if self.interface != "ollama" and "num_ctx" in self.request_parameters:
            message = "num_ctx requires the native ollama interface"
            raise ValueError(message)
        if self.interface == "ollama" and "reasoning_effort" in self.request_parameters:
            message = "reasoning_effort requires the openai interface"
            raise ValueError(message)
        if self.base_url:
            url = urlsplit(self.base_url)
            if url.scheme not in {"http", "https"} or not url.hostname:
                message = "base_url must be an absolute HTTP URL"
                raise ValueError(message)
            if url.username or url.password or url.query or url.fragment:
                message = "base_url must not contain credentials, query parameters or fragments"
                raise ValueError(message)
        return self


class ImageInput(BoundaryModel):
    """Carry a content hash and metadata-free, orientation-corrected PNG pixels."""

    image_hash: ContentRevision
    png: bytes
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class OCRLine(BoundaryModel):
    """Retain one original OCR line and its enclosing pixel rectangle."""

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)


class TranscriptionResult(BoundaryModel):
    """Preserve output, geometry, provenance and billing even for failed generations."""

    text: str
    lines: tuple[OCRLine, ...] = ()
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    backend: TranscriptionBackend
    model: str = ""
    mode: TranscriptionMode = "ocr"
    finish_reason: str = "stop"
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    error: str | None = None
    quality_issues: tuple[TranscriptionIssue, ...] = ()

    @model_validator(mode="after")
    def validate_boxes(self) -> Self:
        """Reject malformed or out-of-image OCR coordinates at the typed boundary."""
        for line in self.lines:
            ImageRegion(bbox=line.bbox, width=self.width, height=self.height)
        return self


class TranscriptionRecord(TranscriptionResult):
    """Index recorded text and OCR geometry by the original image bytes only."""

    image_hash: ContentRevision


class TranscriptionRecording(BoundaryModel):
    """Keep reproducible source attribution with deterministic content lookup."""

    model: str
    recorded_at: str
    prompt_version: str
    source: str
    records: tuple[TranscriptionRecord, ...]

    @model_validator(mode="after")
    def validate_hashes(self) -> Self:
        """Reject ambiguous image keys instead of silently selecting a response."""
        hashes = [record.image_hash for record in self.records]
        if len(hashes) != len(set(hashes)):
            message = "records: duplicate image_hash"
            raise ValueError(message)
        return self
