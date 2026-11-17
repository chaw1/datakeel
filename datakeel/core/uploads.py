# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen requests and resumable upload receipts."""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from datakeel.core.evidence_inputs import IMAGE_SUFFIXES

_MAX_CHUNKS = 100_000
# Common file systems cap one path component at 255 bytes, not 255 characters.
_MAX_FILENAME_BYTES = 255
_MAX_RELATIVE_PATH_BYTES = 1024
_MAX_FOLDER_FILES = 2_000


class UploadFolderFile(BaseModel):
    """Describe one relative member of a concatenated image folder upload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=_MAX_RELATIVE_PATH_BYTES)
    size: int = Field(ge=0, strict=True)

    @field_validator("path")
    @classmethod
    def split_relative_path(cls, value: str) -> str:
        """Validate logical identities even though they never name staging files."""
        split, *parts = value.split("/")
        if (
            not parts
            or split not in {"train", "val", "test"}
            or "\\" in value
            or "\0" in value
            or len(value.encode()) > _MAX_RELATIVE_PATH_BYTES
            or any(
                part in {"", ".", ".."} or len(part.encode()) > _MAX_FILENAME_BYTES
                for part in parts
            )
        ):
            message = "Folder files must have a portable relative path under train/, val/ or test/"
            raise ValueError(message)
        if PurePosixPath(value).suffix.lower() not in IMAGE_SUFFIXES | {".txt", ".json"}:
            message = "Folder upload accepts image, text and JSON sidecar files"
            raise ValueError(message)
        return value


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
    folder: tuple[UploadFolderFile, ...] | None = Field(
        default=None, min_length=1, max_length=_MAX_FOLDER_FILES
    )

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

    @model_validator(mode="after")
    def complete_folder(self) -> "UploadInput":
        """Require an unambiguous complete partition of the uploaded blob."""
        if self.folder is None:
            return self
        paths = {PurePosixPath(item.path) for item in self.folder}
        if len(paths) != len(self.folder) or any(
            paths.intersection(path.parents) for path in paths
        ):
            message = "Folder manifest contains duplicate or conflicting paths"
            raise ValueError(message)
        if not any(path.suffix.lower() in IMAGE_SUFFIXES for path in paths):
            message = "Folder manifest contains no supported images"
            raise ValueError(message)
        if sum(item.size for item in self.folder) != self.total_bytes:
            message = "Folder manifest byte count does not match total_bytes"
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
