# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable graph extraction inputs, raw responses and replay metadata."""

import hashlib
from typing import Self

from pydantic import Field, JsonValue, model_validator

from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.models import BoundaryModel


class TextBlock(BoundaryModel):
    """Carry normalized source text and half-open offsets in its entire document."""

    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> Self:
        """Keep offsets and Unicode code-point length consistent."""
        if self.end - self.start != len(self.text):
            msg = "Text block offsets must equal its code-point length"
            raise ValueError(msg)
        return self

    @property
    def content_hash(self) -> str:
        """Hash only content so moving a file cannot invalidate extraction."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class RawExtraction(BoundaryModel):
    """Preserve model claims before schema filtering and source verification."""

    entities: tuple[ExtractedEntity, ...] = ()
    relations: tuple[ExtractedRelation, ...] = ()


class ExtractionResult(BoundaryModel):
    """Carry raw output and observed usage without concealing truncation."""

    output: RawExtraction
    finish_reason: str = "stop"
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    ignored_top_level_keys: int = Field(default=0, ge=0)


class RecordingRecord(ExtractionResult):
    """Bind one recorded response to content, retaining original scorer evidence."""

    text_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    original: JsonValue | None = None


class Recording(BoundaryModel):
    """Keep model, date, prompt and source attribution alongside replay responses."""

    model: str
    recorded_at: str
    prompt_version: str
    source: str
    records: tuple[RecordingRecord, ...]

    @model_validator(mode="after")
    def validate_hashes(self) -> Self:
        """Reject ambiguous duplicate content keys rather than silently replacing output."""
        hashes = [record.text_hash for record in self.records]
        if len(hashes) != len(set(hashes)):
            msg = "records: duplicate text_hash"
            raise ValueError(msg)
        return self
