# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve only version-owned uploaded training files and fresh backend bytes."""

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.llm_data_models import TrainingSource
from datakeel.core.models import FileItem
from datakeel.storage.database import VersionRow
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.file_state import get_file_state
from datakeel.storage.objects import digest, fresh_object, object_store


def source_version(session: Session, dataset_id: str, version_id: str | None) -> VersionRow:
    """Require an explicit owned version or resolve the latest existing immutable manifest."""
    require_dataset(session, dataset_id)
    row = (
        session.get(VersionRow, version_id)
        if version_id
        else session.scalar(
            select(VersionRow)
            .where(VersionRow.dataset_id == dataset_id)
            .order_by(VersionRow.created_at.desc(), VersionRow.id)
            .limit(1)
        )
    )
    if row is None or row.dataset_id != dataset_id:
        msg = "Training source version not found"
        raise NotFoundError(msg)
    return row


def source_files(
    session: Session, version: VersionRow, identifiers: tuple[str, ...], *, evaluation: bool = False
) -> tuple[FileItem, ...]:
    """Validate exact file identities and reject hidden, deleted or unsupported inputs."""
    wanted = set(identifiers)
    files = tuple(
        FileItem.model_validate(value)
        for value in version.manifest
        if (not wanted or value["id"] in wanted)
        and (wanted or Path(str(value["filename"])).suffix.lower() == ".jsonl")
    )
    if wanted and {item.id for item in files} != wanted:
        msg = "A selected training source file does not belong to the version"
        raise NotFoundError(msg)
    suffixes = {".jsonl", ".txt", ".text"} if evaluation else {".jsonl"}
    for item in files:
        state = get_file_state(session, version.dataset_id, item.id)
        if state.deleted or state.quarantined:
            msg = "Deleted or quarantined training inputs are unavailable"
            raise ValidationError(msg)
        if Path(item.filename).suffix.lower() not in suffixes:
            msg = "Training files must be JSONL; evaluations accept JSONL or text"
            raise ValidationError(msg)
        if not isinstance(item.metadata.get("object_key"), str):
            msg = "Training inputs require uploaded object references"
            raise ValidationError(msg)
    return files


@contextmanager
def fresh_sources(files: tuple[FileItem, ...]) -> Generator[tuple[TrainingSource, ...]]:
    """Keep backend reads alive for the streaming engine, bypassing stale download caches."""
    store = object_store()
    with ExitStack() as stack:
        sources = tuple(
            TrainingSource(
                file_id=item.id,
                filename=item.filename,
                path=str(stack.enter_context(fresh_object(store, item.metadata["object_key"]))),
            )
            for item in files
        )
        _verify_source_bytes(sources, files)
        yield sources
        _verify_source_bytes(sources, files)


def _verify_source_bytes(sources: tuple[TrainingSource, ...], files: tuple[FileItem, ...]) -> None:
    for source, file in zip(sources, files, strict=True):
        if file.sha256 and digest(Path(source.path)) != file.sha256:
            msg = "Uploaded training source bytes changed from their immutable manifest"
            raise ConflictError(msg)
