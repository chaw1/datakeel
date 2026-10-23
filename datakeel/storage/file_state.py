# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authoritative mutable file state layered over immutable manifest versions."""

from collections.abc import Sequence

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from datakeel.core.models import BoundaryModel, FileItem
from datakeel.storage.base import Base


class FileStateRow(Base):
    """Persist logical quarantine/deletion state shared by all file versions."""

    __tablename__ = "file_states"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), primary_key=True)
    file_id: Mapped[str] = mapped_column(String, primary_key=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class FileStateView(BoundaryModel):
    """Expose the revisioned overlay without returning a database row."""

    quarantined: bool = False
    deleted: bool = False
    revision: int = 0


def get_file_state(session: Session, dataset_id: str, file_id: str) -> FileStateView:
    """Read a stored overlay or the implicit original file state."""
    row = session.get(FileStateRow, (dataset_id, file_id))
    if row is None:
        return FileStateView()
    return FileStateView(quarantined=row.quarantined, deleted=row.deleted, revision=row.revision)


def overlay_files(
    session: Session, dataset_id: str, files: Sequence[FileItem], *, include_deleted: bool = False
) -> list[FileItem]:
    """Apply shared file state and hide logical deletions from normal reads."""
    result: list[FileItem] = []
    for item in files:
        if session.get(FileStateRow, (dataset_id, item.id)) is None:
            result.append(item)
            continue
        state = get_file_state(session, dataset_id, item.id)
        if not include_deleted and state.deleted:
            continue
        result.append(
            item.model_copy(
                update={
                    "metadata": {
                        **item.metadata,
                        "quarantined": state.quarantined,
                        "deleted": state.deleted,
                        "state_revision": state.revision,
                    }
                }
            )
        )
    return result
