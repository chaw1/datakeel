# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public object properties whose JSON Schemas define the ontology registry."""

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel
from datakeel.storage.views import DatasetView


class DatasetProperties(DatasetView):
    """Dataset summary addressed by the existing dataset asset identity."""

    dataset_id: str


class FileProperties(BoundaryModel):
    """Public file evidence with live disposition and reproducible quality."""

    id: str
    dataset_id: str
    version_id: str
    filename: str
    path: str
    modality: str
    size: int
    sha256: str
    metadata: dict[str, JsonValue]
    quality: float = Field(
        description=(
            "Per-file rule score, 0-100. Empty/unreadable files score zero. "
            "Recorded text length and printable-character evidence cap the score."
        )
    )
    quarantined: bool
    deleted: bool
    created_at: float


class VersionProperties(BoundaryModel):
    """Immutable version summary without a second copy of its manifest."""

    id: str
    dataset_id: str
    version_id: str
    file_count: int
    created_at: float
    task_id: str | None
    size: int


class TaskProperties(BoundaryModel):
    """Durable task state and its selected input snapshot."""

    id: str
    dataset_id: str
    state: str
    queue: str
    created_at: float
    version_id: str | None
