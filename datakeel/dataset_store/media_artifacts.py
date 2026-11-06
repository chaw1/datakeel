# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist point-cloud preview sidecars without exposing private materialized paths."""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from datakeel.core.models import FileItem, Record
from datakeel.storage.objects import digest

if TYPE_CHECKING:
    from datakeel.storage.objects import ObjectStore


class PreviewArtifact(Record):
    """Describe a generated PNG before and after content-addressed persistence."""

    artifact_id: str
    path: str | None = None
    filename: str
    sha256: str
    size: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    object_key: str | None = None


def persist_preview(item: FileItem, store: "ObjectStore") -> FileItem:
    """Store a preview sidecar and replace its private path with an immutable object key."""
    raw = item.metadata.get("pointcloud_preview")
    if raw is None:
        return item
    preview = PreviewArtifact.model_validate(raw)
    if preview.path is None:
        return item
    path = Path(preview.path)
    checksum = digest(path)
    key = f"{checksum[:2]}/{checksum}.png"
    store.put(path, key)
    saved = preview.model_copy(
        update={"path": None, "sha256": checksum, "size": path.stat().st_size, "object_key": key}
    )
    return item.model_copy(
        update={
            "metadata": {**item.metadata, "pointcloud_preview": saved.model_dump(exclude_none=True)}
        }
    )
