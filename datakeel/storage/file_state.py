# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authoritative mutable file state layered over immutable manifest versions."""

from collections.abc import Sequence

from sqlalchemy import Boolean, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from datakeel.core.models import BoundaryModel, FileItem
from datakeel.storage.base import Base

_MAX_BOUNDED_OVERLAY = 1000


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


def _bindable(session: Session, identifier: str) -> bool:
    if session.get_bind().dialect.name == "postgresql" and "\0" in identifier:
        return False
    try:
        identifier.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def overlay_files(
    session: Session, dataset_id: str, files: Sequence[FileItem], *, include_deleted: bool = False
) -> list[FileItem]:
    """Apply shared file state and hide logical deletions from normal reads."""
    if not files:
        return []
    statement = select(FileStateRow).where(FileStateRow.dataset_id == dataset_id)
    if len(files) <= _MAX_BOUNDED_OVERLAY and all(_bindable(session, item.id) for item in files):
        statement = statement.where(FileStateRow.file_id.in_({item.id for item in files}))
    states = {row.file_id: row for row in session.scalars(statement)}
    result: list[FileItem] = []
    for item in files:
        state = states.get(item.id)
        if state is None:
            result.append(item)
            continue
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
