# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read annotation history in the upright frame without rewriting immutable rows.

Up to v0.18.0 the workbench drew images in stored pixel order, so revisions saved then are in
the stored frame. Their rows carry no ``coordinate_frame`` (NULL); rows written since carry
``display``. Reading a NULL row of an EXIF-oriented image converts it on the fly and records
the exact transform in ``coordinate_conversion``. Nothing is written back, so the history and
audit stay byte-identical and repeated upgrades or reads never convert twice.
"""

from typing import TYPE_CHECKING

from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.image_orientation import (
    CoordinateFrame,
    ImageGeometry,
    conversion,
    display_record,
)
from datakeel.core.models import FileItem
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.database import VersionRow
from datakeel.storage.image_geometry import file_geometry
from datakeel.storage.production_rows import ProductionProjectRow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datakeel.core.annotation_models import AnnotationRecord
    from datakeel.storage.annotation_rows import AnnotationBatchRow
    from datakeel.storage.production_rows import ProductionRevisionRow

DISPLAY_FRAME: CoordinateFrame = "display"
_FILES = "datakeel.version_files"
_PROJECTS = "datakeel.project_versions"


def version_files(session: "Session", version_id: str) -> dict[str, FileItem]:
    """Index one immutable version's manifest by sample id, once per session."""
    cache: dict[str, dict[str, FileItem]] = session.info.setdefault(_FILES, {})
    if version_id not in cache:
        row = session.get(VersionRow, version_id)
        items = (FileItem.model_validate(item) for item in (row.manifest if row else ()))
        cache[version_id] = {item.id: item for item in items}
    return cache[version_id]


def sample_geometry(session: "Session", version_id: str, sample_id: str) -> ImageGeometry | None:
    """Return a version sample's upright geometry; None for non-images or unreadable files."""
    file = version_files(session, version_id).get(sample_id)
    return file_geometry(file) if file is not None else None


def legacy_record(
    session: "Session", version_id: str, record: "AnnotationRecord"
) -> tuple["AnnotationRecord", ImageGeometry | None]:
    """Convert one stored-frame record; return the geometry only when a transform applied."""
    geometry = sample_geometry(session, version_id, record.sample_id)
    if geometry is None or geometry.orientation == 1:
        return record, None
    return display_record(record, geometry), geometry


def _project_version(session: "Session", project_id: str) -> str | None:
    cache: dict[str, str | None] = session.info.setdefault(_PROJECTS, {})
    if project_id not in cache:
        row = session.get(ProductionProjectRow, project_id)
        cache[project_id] = Project.model_validate(row.payload).version_id if row else None
    return cache[project_id]


def revision_view(session: "Session", row: "ProductionRevisionRow") -> AnnotationRevision:
    """Read a revision in the upright frame, converting legacy stored-frame rows on read."""
    revision = AnnotationRevision.model_validate(row.payload)
    if row.coordinate_frame == DISPLAY_FRAME:
        return revision
    version_id = _project_version(session, row.project_id)
    if version_id is None:
        return revision
    annotation, geometry = legacy_record(session, version_id, revision.annotation)
    if geometry is None:
        return revision
    return revision.model_copy(
        update={"annotation": annotation, "coordinate_conversion": conversion(geometry)}
    )


def batch_view(session: "Session", row: "AnnotationBatchRow") -> AnnotationBatch:
    """Read a dataset annotation batch in the upright frame.

    Batches imported before v0.19 were shown on stored pixels, so they are stored-frame data
    and are converted on read exactly like legacy revisions; the stored batch never changes.
    """
    batch = AnnotationBatch.model_validate(row.batch)
    if row.coordinate_frame == DISPLAY_FRAME:
        return batch
    records = tuple(
        legacy_record(session, row.version_id, record)[0] for record in batch.annotations
    )
    return batch.model_copy(update={"annotations": records})
