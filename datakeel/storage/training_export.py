# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve and fingerprint version-bound training export facts inside action transactions."""

from typing import cast

from sqlalchemy.orm import Session

from datakeel.actions.parameters import ExportParams
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import FileItem
from datakeel.core.training_export_models import (
    TRAINING_FORMATS,
    TrainingExport,
    TrainingExportItem,
    TrainingFormat,
)
from datakeel.core.training_models import SplitMember, SplitSet
from datakeel.storage.datasets import materialize_files
from datakeel.storage.object_projection import content_digest
from datakeel.storage.release_service import iter_release_entries, require_release
from datakeel.storage.training_rows import TrainingSplitRow
from datakeel.storage.version_stream import require_version, stream_manifest


def _split(session: Session, params: ExportParams) -> SplitSet:
    row = session.get(TrainingSplitRow, params.split_set_id) if params.split_set_id else None
    if row is None or row.dataset_id != params.dataset_id:
        message = "Training exports require an existing split_set_id in this dataset"
        raise NotFoundError(message)
    split = SplitSet.model_validate(row.payload)
    if split.version_id != params.version_id:
        message = "Training split does not belong to the selected source version"
        raise ValidationError(message)
    return split


def prepare_training_export(session: Session, params: ExportParams) -> ExportParams:
    """Resolve a release to its exact version and reject unbound or ambiguous training exports."""
    if params.format not in TRAINING_FORMATS:
        if params.release_id or params.split_set_id or params.annotator_id:
            message = "Training split, release and annotator options require a training format"
            raise ValidationError(message)
        return params
    if params.release_id:
        release = require_release(session, params.release_id)
        if release.dataset_id != params.dataset_id or (
            params.version_id is not None and params.version_id != release.version_id
        ):
            message = "Training release does not match the requested dataset and version"
            raise ValidationError(message)
        params = params.model_copy(update={"version_id": release.version_id})
    if params.version_id is None:
        message = "Training exports must bind an explicit version_id or release_id"
        raise ValidationError(message)
    require_version(session, params.dataset_id, params.version_id)
    training_export_inputs(session, params, materialize=False)
    return params


def _source_files(session: Session, params: ExportParams) -> tuple[FileItem, ...]:
    if params.release_id:
        return tuple(
            FileItem(
                id=entry.file.id,
                path="",
                filename=entry.file.filename,
                sha256=entry.file.sha256,
                size=entry.file.size,
                modality=entry.file.modality,
                metadata={**entry.file.metadata, "object_key": entry.object_key},
            )
            for entry in iter_release_entries(session, params.release_id)
        )
    if params.version_id is None:
        message = "Training export source version is missing"
        raise ValidationError(message)
    require_version(session, params.dataset_id, params.version_id)
    return tuple(stream_manifest(session, params.version_id))


def _annotation(member: SplitMember, annotator_id: str | None) -> AnnotationRecord:
    records = tuple(
        record
        for record in member.annotations
        if annotator_id is None or record.annotator_id == annotator_id
    )
    if len(records) != 1:
        message = "Training exports require one frozen annotation per sample; select annotator_id"
        raise ValidationError(message)
    return records[0]


def training_export_inputs(
    session: Session, params: ExportParams, *, materialize: bool
) -> TrainingExport:
    """Use annotations frozen at split creation, checking membership and original content hashes."""
    split = _split(session, params)
    sources = _source_files(session, params)
    files = {file.id: file for file in (materialize_files(sources) if materialize else sources)}
    if set(files) != {member.sample_id for member in split.members}:
        message = "Training source membership differs from the frozen split"
        raise ConflictError(message)
    modality = "text" if params.format == "text_jsonl" else "image"
    items: list[TrainingExportItem] = []
    for member in split.members:
        file = files[member.sample_id]
        if file.sha256 != member.sha256:
            message = "Training source hash differs from the frozen split"
            raise ConflictError(message)
        if file.modality == modality:
            items.append(
                TrainingExportItem(
                    file=file,
                    split=member.split,
                    annotation=_annotation(member, params.annotator_id),
                )
            )
    if not items:
        message = "The selected version has no files for the requested training format"
        raise ValidationError(message)
    return TrainingExport(
        dataset_id=params.dataset_id,
        version_id=split.version_id,
        release_id=params.release_id,
        split_set_id=split.id,
        seed=split.request.seed,
        format=cast("TrainingFormat", params.format),
        items=tuple(items),
    )


def training_export_state(session: Session, params: ExportParams) -> str:
    """Freeze the complete split and source manifest without reading bytes during plan review."""
    if params.format not in TRAINING_FORMATS:
        return ""
    return content_digest(
        {
            "split": _split(session, params).model_dump(mode="json"),
            "sources": [file.model_dump(mode="json") for file in _source_files(session, params)],
        }
    )
