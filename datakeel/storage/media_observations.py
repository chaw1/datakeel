# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read same-byte media measurements without rewriting immutable source manifests."""

import json
from copy import deepcopy

from pydantic import Field, JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import BoundaryModel, FileItem, JsonDocument
from datakeel.storage.database import VersionRow


def _identity(file: FileItem) -> str:
    return json.dumps([file.id, file.sha256], separators=(",", ":"))


class MediaObservation(BoundaryModel):
    """Bind only measured quality fields to an exact file and content identity."""

    file_id: str
    sha256: str
    metadata: dict[str, JsonValue]


class MediaObservations(BoundaryModel):
    """Index the newest same-byte measurements for current source-file projections."""

    files: dict[str, MediaObservation] = Field(default_factory=dict[str, MediaObservation])

    def observed(self, file: FileItem) -> FileItem:
        """Overlay allowed measurement fields only when both ID and nonempty hash match."""
        observation = self.files.get(_identity(file))
        if observation is None or not file.sha256 or observation.sha256 != file.sha256:
            return file
        return file.model_copy(
            update={
                "metadata": deepcopy(
                    {
                        **file.metadata,
                        **observation.metadata,
                    }
                )
            }
        )


def _measurements(file: FileItem) -> dict[str, JsonValue]:
    values: dict[str, JsonValue] = {}
    image = file.metadata.get("image_quality")
    if isinstance(image, dict) and "overall_score" in image:
        values["image_quality"] = image
        for dimension in ("width", "height"):
            value = file.metadata.get(dimension)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                values[dimension] = value
    cloud = file.metadata.get("pointcloud_probe")
    if isinstance(cloud, dict):
        values["pointcloud_probe"] = cloud
        policy = file.metadata.get("pointcloud_probe_params")
        if isinstance(policy, dict):
            values["pointcloud_probe_params"] = policy
    return JsonDocument.model_validate(values).root


def read_media_observations(session: Session, dataset_id: str) -> MediaObservations:
    """Read newest measured revisions within one dataset into frozen typed observations."""
    observations: dict[str, MediaObservation] = {}
    versions = session.scalars(
        select(VersionRow)
        .where(VersionRow.dataset_id == dataset_id)
        .order_by(VersionRow.created_at.desc(), VersionRow.id.desc())
    )
    for version in versions:
        for raw in version.manifest:
            file = FileItem.model_validate(raw)
            identity = _identity(file)
            if not file.sha256 or identity in observations:
                continue
            measured = _measurements(file)
            if measured:
                observations[identity] = MediaObservation(
                    file_id=file.id,
                    sha256=file.sha256,
                    metadata=measured,
                )
    return MediaObservations(files=observations)
