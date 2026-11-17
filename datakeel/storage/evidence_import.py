# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import generated or user-supplied paired samples into immutable object storage."""

from pathlib import Path, PurePosixPath

from sqlalchemy import select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_inputs import IMAGE_SUFFIXES
from datakeel.core.models import FileItem, JsonDocument
from datakeel.dataset_store.datasets import dataset_dict, prepare_paired_images, publish_files
from datakeel.dataset_store.rows import VersionRow
from datakeel.datasets.views import DatasetView
from datakeel.storage.database import Database

__all__ = ["IMAGE_SUFFIXES", "import_evidence_samples", "source_manifest"]


def import_evidence_samples(db: Database, name: str, directory: Path) -> DatasetView:
    """Freeze image and sidecar contents, retaining only images as selectable samples.

    Caption/annotation identities remain addressable through their source image.
    Gold files and directory names other than the split never supply assertions.
    """
    root = directory.resolve()
    sources: dict[PurePosixPath, Path] = {
        PurePosixPath(path.relative_to(root).as_posix()): path
        for path in root.rglob("*")
        if path.is_file()
    }
    files = prepare_paired_images(sources)
    with db.session() as session:
        dataset = publish_files(
            session, name, files, JsonDocument({"evidence_samples": True}), paired=True
        )
        result = DatasetView.model_validate(dataset_dict(dataset))
        session.commit()
        return result


def source_manifest(db: Database, dataset_id: str) -> tuple[str, list[FileItem]]:
    """Return the original immutable image manifest and its version identity."""
    with db.session() as session:
        version = session.scalar(
            select(VersionRow)
            .where(VersionRow.dataset_id == dataset_id)
            .order_by(VersionRow.created_at, VersionRow.id)
        )
        if version is None:
            msg = "Evidence source version not found"
            raise ValidationError(msg)
        return version.id, [FileItem.model_validate(value) for value in version.manifest]
