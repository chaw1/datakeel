# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset imports and immutable manifest snapshots."""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_inputs import IMAGE_SUFFIXES, SampleSidecars
from datakeel.core.models import AssetRef, FileItem, JsonDocument, LineageEvent
from datakeel.dataset_store.events import append_event
from datakeel.dataset_store.file_state import overlay_files
from datakeel.dataset_store.import_sources import image_dimensions, import_sources
from datakeel.dataset_store.media_artifacts import persist_preview
from datakeel.dataset_store.rows import DatasetRow, VersionRow
from datakeel.datasets.records import PublishedDataset
from datakeel.semantic import classify
from datakeel.storage.objects import ObjectStore, digest, object_store

if TYPE_CHECKING:
    from pydantic import JsonValue


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
    for path, relative in import_sources(paths):
        semantic = classify(path.name)
        modality = semantic.get("modality", "unknown")
        metadata: dict[str, JsonValue] = {"semantic": semantic.model_dump(mode="json")}
        if relative is not None:
            # Only the path under the chosen import root; the machine's own path stays private.
            metadata["relative_path"] = relative
        if modality == "image":
            metadata.update(image_dimensions(path))
        yield persist_file(
            FileItem(
                path=str(path.resolve()),
                filename=path.name,
                modality=modality,
                metadata=metadata,
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
    *,
    paired: bool = False,
) -> PublishedDataset:
    """Publish an already persisted manifest and initial lineage inside one transaction."""
    items = tuple(prepared)
    files = [item.model_dump(mode="json") for item in items]
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
            operator="dataset.import_evidence" if paired else "dataset.import",
            inputs=[
                AssetRef(
                    asset_type="source",
                    asset_id=f"source:{dataset.id}",
                    display_name=None if paired else "Local import",
                )
            ],
            outputs=[AssetRef(asset_id=dataset.id, version=version.id, display_name=name)],
            source_module="storage",
            quality={"file_count": len(files)},
        ),
    )
    return PublishedDataset(
        id=dataset.id,
        name=dataset.name,
        created_at=dataset.created_at,
        files=items,
        metadata_values=dataset.metadata_values,
        quality_config=dataset.quality_config,
        template=dataset.template,
        compliance=dataset.compliance,
    )


def import_dataset(
    session: Session, name: str, paths: list[Path], metadata: dict[str, Any] | None = None
) -> PublishedDataset:
    """Import local files and publish their initial lineage atomically."""
    return publish_files(
        session, name, _prepared_files(paths), JsonDocument.model_validate(metadata or {})
    )


def dataset_dict(dataset: DatasetRow | PublishedDataset) -> dict[str, Any]:
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


def _store_file(
    relative: PurePosixPath, source: Path, modality: str, store: ObjectStore
) -> FileItem:
    return persist_file(
        FileItem(path=str(source), filename=relative.as_posix(), modality=modality), store
    )


def _sidecar(
    paths: tuple[PurePosixPath, ...], sources: Mapping[PurePosixPath, Path], store: ObjectStore
) -> FileItem | None:
    path = next((value for value in paths if value in sources), None)
    return _store_file(path, sources[path], "text", store) if path else None


def _sample(
    path: PurePosixPath, sources: Mapping[PurePosixPath, Path], store: ObjectStore
) -> FileItem:
    first = path.parts[0]
    if first not in {"train", "val", "test"}:
        msg = "Paired samples must be under train/, val/ or test/"
        raise ValidationError(msg)
    split: Literal["train", "val", "test"] = (
        "train" if first == "train" else "test" if first == "test" else "val"
    )
    sidecars = SampleSidecars(
        sample_key=path.as_posix(),
        split=split,
        caption=_sidecar(
            (
                path.with_suffix(".txt"),
                path.parent / "caption.txt",
                path.parent / "caption.json",
                path.with_suffix(".json"),
            ),
            sources,
            store,
        ),
        annotation=_sidecar(
            (
                path.with_suffix(".annotations.json"),
                path.parent / "annotations.json",
                path.with_suffix(".json"),
            ),
            sources,
            store,
        ),
    )
    file = _store_file(path, sources[path], "image", store)
    return file.model_copy(
        update={
            "metadata": {
                **file.metadata,
                "split": split,
                "evidence_sample": sidecars.model_dump(mode="json"),
            }
        }
    )


def prepare_paired_images(sources: Mapping[PurePosixPath, Path]) -> tuple[FileItem, ...]:
    """Persist paired objects while retaining only images as selectable manifest entries."""
    paths = sorted(path for path in sources if path.suffix.lower() in IMAGE_SUFFIXES)
    if not paths:
        msg = "No paired image samples found"
        raise ValidationError(msg)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="import") as pool:
        return tuple(pool.map(_sample, paths, repeat(sources), repeat(object_store())))
