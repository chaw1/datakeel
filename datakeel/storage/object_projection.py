# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project ontology objects directly from authoritative rows and manifests."""

import hashlib
import json
from collections.abc import Iterable

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import AssetRef, FileItem, JsonDocument
from datakeel.ontology.models import FrozenObject, ObjectSet
from datakeel.quality import score_quality
from datakeel.storage.database import DatasetRow, TaskRow, VersionRow
from datakeel.storage.datasets import dataset_dict
from datakeel.storage.evidence_snapshot import EvidenceSnapshot, observed_file, read_snapshot
from datakeel.storage.file_state import get_file_state


def content_digest(value: JsonValue) -> str:
    """Hash canonical JSON without relying on insertion order or runtime identity."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _freeze(
    asset: AssetRef,
    properties: dict[str, JsonValue],
    *,
    revision: JsonValue,
    state_revision: int = 0,
) -> FrozenObject:
    size = properties.get("size", 0)
    return FrozenObject(
        asset_ref=asset,
        revision=content_digest(revision),
        state_revision=state_revision,
        properties=properties,
        size=size if isinstance(size, int) else 0,
    )


def _versions(session: Session, dataset_id: str, query: ObjectSet) -> list[VersionRow]:
    statement = select(VersionRow).where(VersionRow.dataset_id == dataset_id)
    if query.version_ids:
        statement = statement.where(VersionRow.id.in_(query.version_ids))
    if query.created_after:
        statement = statement.where(VersionRow.created_at >= query.created_after.timestamp())
    if query.created_before:
        statement = statement.where(VersionRow.created_at <= query.created_before.timestamp())
    if query.object_type == "artifact":
        statement = statement.where(VersionRow.task_id.is_not(None))
    values = list(session.scalars(statement.order_by(VersionRow.created_at.desc(), VersionRow.id)))
    if (
        query.object_type == "version"
        or query.version_ids
        or query.created_after
        or query.created_before
    ):
        return values
    return values[-1:] if query.object_type == "file" else values[:1]


def has_evidence_sources(
    session: Session, datasets: Iterable[DatasetRow], query: ObjectSet
) -> bool:
    """Detect paired samples from the selected immutable manifests, not user metadata."""
    return any(
        "evidence_sample" in FileItem.model_validate(raw).metadata
        for dataset in datasets
        for version in _versions(session, dataset.id, query)
        for raw in version.manifest
    )


def file_quality(file: FileItem, dataset: DatasetRow) -> float:
    """Score one file; empty or unreadable evidence caps its aggregate score at zero."""
    if not file.size or file.metadata.get("empty") or file.metadata.get("corrupt"):
        return 0.0
    result = score_quality([file], dataset.quality_config).total
    evidence = JsonDocument.model_validate(file.metadata).root.get("text_quality")
    if isinstance(evidence, dict):
        characters, printable = evidence.get("characters"), evidence.get("printable_ratio")
        if isinstance(characters, int) and not isinstance(characters, bool):
            result = min(result, 100 * min(characters / 20, 1))
        if isinstance(printable, int | float) and not isinstance(printable, bool):
            result = min(result, max(0, min(100, printable * 100)))
    return round(result, 2)


def _file_object(
    session: Session, dataset: DatasetRow, version: VersionRow, item: FileItem, query: ObjectSet
) -> FrozenObject | None:
    state = get_file_state(session, dataset.id, item.id)
    if state.deleted and not query.include_deleted:
        return None
    properties: dict[str, JsonValue] = {
        "id": item.id,
        "dataset_id": dataset.id,
        "version_id": version.id,
        "filename": item.filename,
        "path": item.filename,
        "modality": item.modality,
        "size": item.size,
        "sha256": item.sha256,
        "metadata": item.metadata,
        "quality": file_quality(item, dataset),
        "quarantined": state.quarantined,
        "deleted": state.deleted,
        "created_at": version.created_at,
    }
    return _freeze(
        AssetRef(
            asset_type=query.object_type,
            asset_id=item.id,
            version=version.id,
            display_name=item.filename,
        ),
        properties,
        revision={
            "properties": properties,
            "state_revision": state.revision,
            "quality_config": dataset.quality_config,
        },
        state_revision=state.revision,
    )


def _file_objects(
    session: Session, dataset: DatasetRow, query: ObjectSet, snapshot: EvidenceSnapshot
) -> list[FrozenObject]:
    result: list[FrozenObject] = []
    for version in _versions(session, dataset.id, query):
        for raw in version.manifest:
            file = observed_file(FileItem.model_validate(raw), version.id, snapshot)
            value = _file_object(session, dataset, version, file, query)
            if value is not None:
                result.append(value)
    return result


def _version_objects(session: Session, dataset: DatasetRow, query: ObjectSet) -> list[FrozenObject]:
    result: list[FrozenObject] = []
    for version in _versions(session, dataset.id, query):
        properties: dict[str, JsonValue] = {
            "id": version.id,
            "dataset_id": dataset.id,
            "version_id": version.id,
            "file_count": len(version.manifest),
            "created_at": version.created_at,
            "task_id": version.task_id,
            "size": sum(FileItem.model_validate(raw).size for raw in version.manifest),
        }
        result.append(
            _freeze(
                AssetRef(asset_type="version", asset_id=version.id, version=version.id),
                properties,
                revision=JsonDocument.model_validate(
                    {"properties": properties, "manifest": version.manifest}
                ).root,
            )
        )
    return result


def _task_objects(session: Session, dataset: DatasetRow) -> list[FrozenObject]:
    result: list[FrozenObject] = []
    for task in session.scalars(select(TaskRow).where(TaskRow.dataset_id == dataset.id)):
        properties: dict[str, JsonValue] = {
            "id": task.id,
            "dataset_id": task.dataset_id,
            "state": task.state,
            "queue": task.queue,
            "created_at": task.created_at,
            "version_id": task.input_version_id,
        }
        result.append(
            _freeze(AssetRef(asset_type="task", asset_id=task.id), properties, revision=properties)
        )
    return result


def project_objects(
    session: Session,
    datasets: Iterable[DatasetRow],
    query: ObjectSet,
    snapshot: EvidenceSnapshot | None = None,
) -> list[FrozenObject]:
    """Resolve each supported object type without writing ontology instance tables."""
    result: list[FrozenObject] = []
    snapshot = snapshot or read_snapshot(session)
    for dataset in datasets:
        if query.object_type in {"file", "artifact"}:
            result.extend(_file_objects(session, dataset, query, snapshot))
        elif query.object_type == "version":
            result.extend(_version_objects(session, dataset, query))
        elif query.object_type == "task":
            result.extend(_task_objects(session, dataset))
        else:
            properties = dataset_dict(dataset)
            properties["dataset_id"] = dataset.id
            result.append(
                _freeze(
                    AssetRef(asset_id=dataset.id, display_name=dataset.name),
                    properties,
                    revision=properties,
                )
            )
    return result
