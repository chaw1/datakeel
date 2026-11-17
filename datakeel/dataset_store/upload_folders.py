# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stage checked folder members under server-owned names before paired publication."""

from pathlib import Path, PurePosixPath
from typing import BinaryIO

from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_inputs import CocoDocument, sample_sidecars
from datakeel.core.models import FileItem
from datakeel.core.uploads import UploadFolderFile
from datakeel.dataset_store.datasets import prepare_paired_images

_COPY_BYTES = 1024 * 1024
_MAX_ANNOTATION_BYTES = 16 * _COPY_BYTES


def _copy_member(source: BinaryIO, target: Path, size: int) -> None:
    with target.open("wb") as output:
        while size:
            chunk = source.read(min(size, _COPY_BYTES))
            if not chunk:
                message = "Folder member bytes ended before their declared size"
                raise ValidationError(message)
            output.write(chunk)
            size -= len(chunk)


def _annotation_labels(source: FileItem | None) -> list[str] | None:
    if source is None:
        return None
    with Path(source.path).open("rb") as stream:
        content = stream.read(_MAX_ANNOTATION_BYTES + 1)
    if len(content) > _MAX_ANNOTATION_BYTES:
        return None
    try:
        annotations = CocoDocument.model_validate_json(content).annotations
    except ModelValidationError:
        return None
    return sorted({annotation.category for annotation in annotations})


def _finalize_image(file: FileItem) -> FileItem:
    sidecars = sample_sidecars(file)
    labels = _annotation_labels(sidecars.annotation)
    portable = {
        name: source.model_copy(update={"path": source.filename})
        for name, source in (("caption", sidecars.caption), ("annotation", sidecars.annotation))
        if source is not None
    }
    sidecars = sidecars.model_copy(update=portable)
    metadata = {**file.metadata, "evidence_sample": sidecars.model_dump(mode="json")}
    if labels is not None:
        metadata["labels"] = labels
    return file.model_copy(
        update={
            "path": file.filename,
            "metadata": metadata,
        }
    )


def prepare_uploaded_folder(
    payload: Path, members: tuple[UploadFolderFile, ...]
) -> tuple[FileItem, ...]:
    """Reconstruct declared logical paths without ever resolving them on the host."""
    directory = payload.parent / "members"
    directory.mkdir()
    sources: dict[PurePosixPath, Path] = {}
    with payload.open("rb") as source:
        for index, member in enumerate(members):
            logical = PurePosixPath(member.path)
            target = directory / f"{index}{logical.suffix.lower()}"
            _copy_member(source, target, member.size)
            sources[logical] = target
    return tuple(_finalize_image(file) for file in prepare_paired_images(sources))
