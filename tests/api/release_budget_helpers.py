# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build a version larger than the default controlled-action object budget."""

from pathlib import Path

from sqlalchemy import select

from datakeel.core.models import FileItem
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import import_paths

FILES = 10_005
GIB = 1024**3


def large_version(db: Database, tmp_path: Path) -> tuple[str, str]:
    """Freeze more files than the 10,000-object default, all backed by one stored object."""
    path = tmp_path / "large.txt"
    path.write_text("Generated large-release sample.", encoding="utf-8")
    dataset = import_paths(db, "large-release", [path])
    with db.session() as session:
        version = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        assert version is not None
        template = FileItem.model_validate(version.manifest[0])
        version.manifest = [
            template.model_copy(update={"id": f"file-{index:05d}"}).model_dump(mode="json")
            for index in range(FILES)
        ]
        session.commit()
        return dataset.id, version.id
