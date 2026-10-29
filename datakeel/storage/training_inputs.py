# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read verified version content and immutable annotation batches into training facts."""

import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord, AnnotationSpan
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import AssetRef, FileItem, JsonDocument
from datakeel.core.training_models import TrainingSample
from datakeel.operators.evidence.image_phash import dhash
from datakeel.operators.image.helpers import open_image
from datakeel.storage.annotation_legacy import annotation_from_file
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.data_asset_access import require_access_in_session
from datakeel.storage.database import Database
from datakeel.storage.datasets import materialize_files
from datakeel.storage.objects import digest
from datakeel.storage.version_stream import require_version, stream_manifest
from datakeel.training.text_hashes import simhash

if TYPE_CHECKING:
    from pydantic import JsonValue

UNIFORM_STD_THRESHOLD = 3


def authorize_training(
    session: Session,
    dataset_id: str,
    version_id: str,
    access: AccessContext | None,
    sample_ids: tuple[str, ...] = (),
) -> None:
    """Apply the native grant policy before exposing any source content or annotation."""
    require_access_in_session(
        session,
        (
            AssetRef(asset_id=dataset_id, version=version_id),
            AssetRef(asset_type="version", asset_id=version_id, version=version_id),
            *(
                AssetRef(asset_type="file", asset_id=sample_id, version=version_id)
                for sample_id in sample_ids
            ),
        ),
        access or AccessContext(actor="local-user", entry="agent", scope="query"),
        record=False,
    )


def _annotations(
    session: Session, dataset_id: str, version_id: str
) -> dict[str, tuple[AnnotationRecord, ...]]:
    rows = session.scalars(
        select(AnnotationBatchRow)
        .where(
            AnnotationBatchRow.dataset_id == dataset_id, AnnotationBatchRow.version_id == version_id
        )
        .order_by(AnnotationBatchRow.created_at.desc(), AnnotationBatchRow.id.desc())
    )
    selected: dict[tuple[str, str], AnnotationRecord] = {}
    for row in rows:
        for record in AnnotationBatch.model_validate(row.batch).annotations:
            selected.setdefault((record.sample_id, record.annotator_id), record)
    grouped: dict[str, list[AnnotationRecord]] = defaultdict(list)
    for key, record in sorted(selected.items()):
        grouped[key[0]].append(record)
    return {sample: tuple(records) for sample, records in grouped.items()}


def _fallback(file: FileItem) -> tuple[AnnotationRecord, ...]:
    record = annotation_from_file(file, "default")
    metadata = JsonDocument.model_validate(file.metadata).root
    labels = metadata.get("labels", metadata.get("label"))
    if isinstance(labels, str):
        labels = [labels]
    if isinstance(labels, list) and all(isinstance(label, str) for label in labels):
        record = record.model_copy(
            update={"labels": tuple(label for label in labels if isinstance(label, str))}
        )
    spans = metadata.get("spans")
    if isinstance(spans, list):
        record = record.model_copy(
            update={"spans": tuple(AnnotationSpan.model_validate(span) for span in spans)}
        )
    return (record,)


def _group(file: FileItem, field: str | None) -> str | None:
    if field is None:
        return None
    value: JsonValue = JsonDocument.model_validate(file.metadata).root
    for segment in field.removeprefix("metadata.").split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if value is not None
        else None
    )


def _image_signal(file: FileItem) -> tuple[int, bool, tuple[int, int, int]]:
    try:
        with open_image(file) as image:
            image_hash = int(dhash(image), 16)
            pixels = np.asarray(image.convert("RGB").resize((32, 32)), dtype=np.float64)
            mean = np.mean(pixels, axis=(0, 1))
            color = (round(float(mean[0])), round(float(mean[1])), round(float(mean[2])))
            uniform = float(np.max(np.std(pixels, axis=(0, 1)))) < UNIFORM_STD_THRESHOLD
            return image_hash, uniform, color
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        message = f"Training image could not be decoded: {file.id}"
        raise ValidationError(message) from error


def _sample(
    file: FileItem, records: tuple[AnnotationRecord, ...], group_field: str | None
) -> TrainingSample:
    checksum = digest(Path(file.path))
    if file.sha256 and file.sha256 != checksum:
        message = "Training source content does not match its immutable version hash"
        raise ConflictError(message)
    file = file.model_copy(update={"sha256": checksum})
    image_hash = None
    text_hash = None
    image_uniform, image_color = False, None
    if file.modality == "image":
        image_hash, image_uniform, image_color = _image_signal(file)
    if file.modality == "text":
        try:
            text_hash = simhash(Path(file.path).read_bytes().decode("utf-8-sig"))
        except UnicodeError as error:
            message = f"Training text is not UTF-8: {file.id}"
            raise ValidationError(message) from error
    labels = tuple(
        sorted(
            {
                label
                for record in records
                for label in (
                    *(record.labels or ()),
                    *(box.category for box in record.boxes or ()),
                    *(polygon.category for polygon in record.polygons or ()),
                    *(span.category for span in record.spans or ()),
                )
            }
        )
    )
    return TrainingSample(
        file=file,
        annotations=records,
        labels=labels,
        group=_group(file, group_field),
        image_hash=image_hash,
        image_uniform=image_uniform,
        image_color=image_color,
        text_hash=text_hash,
    )


def _directory_split(file: FileItem) -> FileItem:
    if "split" in file.metadata:
        return file
    parts = (*Path(file.filename).parts[:-1], *reversed(Path(file.path).parts[:-1]))
    split = next((part for part in parts if part in {"train", "val", "test"}), None)
    return (
        file.model_copy(update={"metadata": {**file.metadata, "split": split}}) if split else file
    )


def read_training_samples(
    session: Session,
    dataset_id: str,
    version_id: str,
    group_field: str | None = None,
    *,
    access: AccessContext | None = None,
) -> tuple[TrainingSample, ...]:
    """Materialize verified version files after checking ownership and current data grants."""
    require_version(session, dataset_id, version_id)
    files = tuple(_directory_split(file) for file in stream_manifest(session, version_id))
    authorize_training(session, dataset_id, version_id, access, tuple(file.id for file in files))
    annotations = _annotations(session, dataset_id, version_id)
    return tuple(
        _sample(file, annotations.get(file.id) or _fallback(file), group_field)
        for file in materialize_files(files)
    )


def load_training_samples(
    db: Database,
    dataset_id: str,
    version_id: str,
    group_field: str | None = None,
    *,
    access: AccessContext | None = None,
) -> tuple[TrainingSample, ...]:
    """Read training facts in an independent short-lived read transaction."""
    with db.session() as session:
        return read_training_samples(session, dataset_id, version_id, group_field, access=access)
