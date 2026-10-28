# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen requests and resumable upload receipts."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

_MAX_CHUNKS = 100_000
# Common file systems cap one path component at 255 bytes, not 255 characters.
_MAX_FILENAME_BYTES = 255


class UploadInput(BaseModel):
    """Declare one file's immutable identity before sending bounded chunks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    idempotency_key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    total_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_bytes: int = Field(gt=0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("filename")
    @classmethod
    def plain_filename(cls, value: str) -> str:
        """Keep upload names independent of private paths and storable as one staging file."""
        if PurePosixPath(value).name != value or value in {".", ".."} or "\\" in value:
            message = "Filename must be a plain basename"
            raise ValueError(message)
        if "\0" in value or len(value.encode()) > _MAX_FILENAME_BYTES:
            message = "Filename must not contain NUL and must fit in 255 UTF-8 bytes"
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def bounded_chunks(self) -> "UploadInput":
        """Bound receipt and missing-chunk lists even with tiny requested chunks."""
        if self.chunk_count > _MAX_CHUNKS:
            message = "Upload exceeds 100000 chunks; choose a larger chunk size"
            raise ValueError(message)
        return self

    @property
    def chunk_count(self) -> int:
        """Return the exact number of chunks, including a partial final chunk."""
        return (self.total_bytes + self.chunk_bytes - 1) // self.chunk_bytes


class UploadView(BaseModel):
    """Expose durable progress without physical paths or uploaded data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    filename: str
    total_bytes: int
    sha256: str
    chunk_bytes: int
    chunk_count: int
    received_chunks: list[int]
    missing_chunks: list[int]
    state: Literal["UPLOADING", "COMPLETE"]
    dataset_id: str | None = None
