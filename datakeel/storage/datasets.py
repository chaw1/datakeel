# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset imports and immutable manifest snapshots."""

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import AssetRef, FileItem, JsonDocument, LineageEvent
from datakeel.semantic import classify
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.events import append_event
from datakeel.storage.file_state import overlay_files
from datakeel.storage.media_artifacts import persist_preview
from datakeel.storage.objects import ObjectStore, digest, object_store


def persist_file(item: FileItem, store: ObjectStore | None = None) -> FileItem:
    """Store file content and return reproducible object evidence."""
    path = Path(item.path)
    checksum = digest(path)
    key = f"{checksum[:2]}/{checksum}{path.suffix.lower()}"
    store = store or object_store()
    item = persist_preview(item, store)
    store.put(path, key)
    return item.model_copy(
        update={
            "sha256": checksum,
            "size": path.stat().st_size,
            "metadata": {**item.metadata, "object_key": key},
        }
    )


def persist_files(items: Sequence[FileItem]) -> list[FileItem]:
    """Persist one manifest with a shared backend for this operation."""
    store = object_store()
    return [persist_file(item, store) for item in items]


def materialize_files(items: Sequence[FileItem | dict[str, Any]]) -> list[FileItem]:
    """Restore manifest objects into locally readable file models."""
    store = object_store()
    paths: dict[str, Path] = {}
    result: list[FileItem] = []
    for value in items:
        item = FileItem.model_validate(value)
        key = item.metadata.get("object_key")
        if key:
            if key not in paths:
                paths[key] = store.materialize(key)
            item = item.model_copy(update={"path": str(paths[key])})
        result.append(item)
    return result


def _prepared_files(paths: Sequence[Path]) -> Iterator[FileItem]:
    store = object_store()
    for path in paths:
        semantic = classify(path.name)
        yield persist_file(
            FileItem(
                path=str(path.resolve()),
                filename=path.name,
                modality=semantic.get("modality", "unknown"),
                metadata={"semantic": semantic.model_dump(mode="json")},
            ),
            store,
        )


def prepare_files(paths: Sequence[Path]) -> tuple[FileItem, ...]:
    """Hash and persist local content without opening a database transaction."""
    return tuple(_prepared_files(paths))


def publish_files(
    session: Session,
    name: str,
    prepared: Iterable[FileItem],
    metadata: JsonDocument | None = None,
) -> DatasetRow:
    """Publish an already persisted manifest and initial lineage inside one transaction."""
    files = [item.model_dump(mode="json") for item in prepared]
    dataset = DatasetRow(name=name, files=files, metadata_values=metadata.root if metadata else {})
    session.add(dataset)
    session.flush()
    version = VersionRow(dataset_id=dataset.id, manifest=files)
    session.add(version)
    session.flush()
    append_event(
        session,
        LineageEvent(
            idempotency_key=f"import:{dataset.id}",
            event_type="IMPORT",
            operator="dataset.import",
            inputs=[
                AssetRef(
                    asset_type="source",
                    asset_id=f"source:{dataset.id}",
                    display_name="Local import",
                )
            ],
            outputs=[AssetRef(asset_id=dataset.id, version=version.id, display_name=name)],
            source_module="storage",
            quality={"file_count": len(files)},
        ),
    )
    return dataset


def import_dataset(
    session: Session, name: str, paths: list[Path], metadata: dict[str, Any] | None = None
) -> DatasetRow:
    """Import local files and publish their initial lineage atomically."""
    return publish_files(
        session, name, _prepared_files(paths), JsonDocument.model_validate(metadata or {})
    )


def dataset_dict(dataset: DatasetRow) -> dict[str, Any]:
    """Serialize an internal dataset row before validation at the service boundary."""
    return {
        "id": dataset.id,
        "name": dataset.name,
        "file_count": len(dataset.files),
        "created_at": dataset.created_at,
        "metadata": dataset.metadata_values,
        "quality_config": dataset.quality_config,
        "template": dataset.template,
        "compliance": dataset.compliance,
    }


def latest_files(session: Session, dataset: DatasetRow) -> list[FileItem]:
    """Read the newest immutable manifest in the current transaction."""
    version = session.scalars(
        select(VersionRow)
        .where(VersionRow.dataset_id == dataset.id)
        .order_by(VersionRow.created_at.desc())
    ).first()
    return overlay_files(
        session,
        dataset.id,
        [
            FileItem.model_validate(value)
            for value in (version.manifest if version else dataset.files)
        ],
    )
