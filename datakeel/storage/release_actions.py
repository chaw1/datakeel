# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze publication state and materialize releases inside approved action transactions."""

import hashlib

from pydantic import JsonValue
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.release_parameters import PublishReleaseParams
from datakeel.core.errors import ConflictError
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument, new_id, utcnow
from datakeel.core.portable_metadata import portable_metadata
from datakeel.core.release_models import VersionSummary
from datakeel.ontology.models import FrozenManifest, FrozenObject, ObjectSet
from datakeel.storage.object_projection import content_digest
from datakeel.storage.objects import digest, fresh_object, object_store
from datakeel.storage.release_rows import ReleaseEntryRow, ReleaseRow
from datakeel.storage.version_diff import version_summary
from datakeel.storage.version_stream import (
    dataset_settings,
    portable_file,
    require_version,
    stream_manifest,
)

BATCH_SIZE = 100


class _ReleaseFacts(BoundaryModel):
    manifest_sha256: str
    storage_sha256: str
    file_count: int
    total_bytes: int
    metadata: dict[str, JsonValue]
    summary: VersionSummary


def _facts(session: Session, params: PublishReleaseParams) -> _ReleaseFacts:
    require_version(session, params.dataset_id, params.version_id, lock=True)
    dataset = dataset_settings(session, params.dataset_id)
    count, size = 0, 0
    checksum = hashlib.sha256()
    storage_checksum = hashlib.sha256()
    for item in stream_manifest(session, params.version_id):
        encoded = portable_file(item, params.version_id).model_dump_json().encode()
        checksum.update(len(encoded).to_bytes(8, "big"))
        checksum.update(encoded)
        storage_checksum.update(str(item.metadata.get("object_key", "")).encode() + b"\0")
        count += 1
        size += item.size
    return _ReleaseFacts(
        manifest_sha256=checksum.hexdigest(),
        storage_sha256=storage_checksum.hexdigest(),
        file_count=count,
        total_bytes=size,
        metadata=portable_metadata(JsonDocument.model_validate(dataset.metadata_values).root),
        summary=version_summary(session, dataset, params.version_id),
    )


def publication_manifest(session: Session, params: PublishReleaseParams) -> FrozenManifest:
    """Bind all version entries and governance facts through a bounded state digest."""
    duplicate = session.scalar(
        select(ReleaseRow.id).where(
            ReleaseRow.dataset_id == params.dataset_id, ReleaseRow.tag == params.tag
        )
    )
    if duplicate is not None:
        message = "Release tag already exists in this dataset"
        raise ConflictError(message)
    facts = _facts(session, params)
    state = content_digest(facts.model_dump(mode="json"))
    return FrozenManifest(
        query=ObjectSet(
            object_type="version", dataset_id=params.dataset_id, version_ids=[params.version_id]
        ),
        objects=[
            FrozenObject(
                asset_ref=AssetRef(
                    asset_type="version", asset_id=params.version_id, version=params.version_id
                ),
                revision=state,
                properties={
                    "dataset_id": params.dataset_id,
                    "version_id": params.version_id,
                    **facts.model_dump(mode="json"),
                },
                size=facts.total_bytes,
            )
        ],
        total_bytes=facts.total_bytes,
        state_digest=state,
    )


def publication_impact(manifest: FrozenManifest) -> int:
    """Count every frozen file for existing action authorization limits."""
    count = manifest.objects[0].properties["file_count"]
    return count if isinstance(count, int) else 0


def _store_entries(session: Session, release_id: str, version_id: str) -> None:
    store = object_store()
    batch: list[dict[str, JsonValue]] = []
    for ordinal, item in enumerate(stream_manifest(session, version_id)):
        key = item.metadata.get("object_key")
        if not isinstance(key, str):
            message = "Published files require a stored object key"
            raise ConflictError(message)
        with fresh_object(store, key) as path:
            if path.stat().st_size != item.size or digest(path) != item.sha256:
                message = "Stored object differs from the version manifest; release refused"
                raise ConflictError(message)
        batch.append(
            {
                "release_id": release_id,
                "file_id": item.id,
                "ordinal": ordinal,
                "object_key": key,
                "record": portable_file(item, version_id).model_dump(mode="json"),
            }
        )
        if len(batch) == BATCH_SIZE:
            session.execute(insert(ReleaseEntryRow), batch)
            batch.clear()
    if batch:
        session.execute(insert(ReleaseEntryRow), batch)


def publish_release(
    session: Session, plan: ActionPlan, params: PublishReleaseParams
) -> OperationResult:
    """Persist verified content and immutable facts only after action approval consumption."""
    frozen = plan.manifest.objects[0].properties
    facts = _ReleaseFacts.model_validate({key: frozen[key] for key in _ReleaseFacts.model_fields})
    identifier = new_id()
    _store_entries(session, identifier, params.version_id)
    session.add(
        ReleaseRow(
            id=identifier,
            dataset_id=params.dataset_id,
            version_id=params.version_id,
            tag=params.tag,
            notes=params.notes,
            created_at=utcnow().timestamp(),
            manifest_sha256=facts.manifest_sha256,
            file_count=facts.file_count,
            total_bytes=facts.total_bytes,
            metadata_values=facts.metadata,
            summary=facts.summary.model_dump(mode="json"),
        )
    )
    session.flush()
    return OperationResult(
        outputs=[AssetRef(asset_type="release", asset_id=identifier, version=params.version_id)],
        details={
            "release_id": identifier,
            "tag": params.tag,
            "manifest_sha256": facts.manifest_sha256,
        },
    )
