# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import generated or user-supplied paired samples into immutable object storage."""

from pathlib import Path

from sqlalchemy import select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_inputs import SampleSidecars
from datakeel.core.models import AssetRef, FileItem, LineageEvent
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.datasets import dataset_dict, persist_file
from datakeel.storage.events import append_event
from datakeel.storage.views import DatasetView

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def _sidecar(paths: list[Path], root: Path) -> FileItem | None:
    path = next((value for value in paths if value.is_file()), None)
    if path is None:
        return None
    return persist_file(
        FileItem(path=str(path), filename=path.relative_to(root).as_posix(), modality="text")
    )


def _paired_file(path: Path, root: Path) -> FileItem:
    relative = path.relative_to(root)
    split = relative.parts[0]
    if split not in {"train", "val"}:
        msg = "Paired samples must be under train/ or val/"
        raise ValidationError(msg)
    sidecars = SampleSidecars(
        sample_key=relative.as_posix(),
        split="train" if split == "train" else "val",
        caption=_sidecar(
            [
                path.with_suffix(".txt"),
                path.parent / "caption.txt",
                path.parent / "caption.json",
                path.with_suffix(".json"),
            ],
            root,
        ),
        annotation=_sidecar(
            [
                path.with_suffix(".annotations.json"),
                path.parent / "annotations.json",
                path.with_suffix(".json"),
            ],
            root,
        ),
    )
    return persist_file(
        FileItem(
            path=str(path),
            filename=relative.as_posix(),
            modality="image",
            metadata={"split": split, "evidence_sample": sidecars.model_dump(mode="json")},
        )
    )


def import_evidence_samples(db: Database, name: str, directory: Path) -> DatasetView:
    """Freeze image and sidecar contents, retaining only images as selectable samples.

    Caption/annotation identities remain addressable through their source image.
    Gold files and directory names other than the split never supply assertions.
    """
    root = directory.resolve()
    files = [
        _paired_file(path, root).model_dump(mode="json")
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    if not files:
        msg = "No paired image samples found"
        raise ValidationError(msg)
    with db.session() as session:
        dataset = DatasetRow(name=name, files=files, metadata_values={"evidence_samples": True})
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
                operator="dataset.import_evidence",
                inputs=[AssetRef(asset_type="source", asset_id=f"source:{dataset.id}")],
                outputs=[AssetRef(asset_id=dataset.id, version=version.id, display_name=name)],
                source_module="storage",
                quality={"file_count": len(files)},
            ),
        )
        result = DatasetView.model_validate(dataset_dict(dataset))
        session.commit()
        return result


def source_manifest(db: Database, dataset_id: str) -> tuple[str, list[FileItem]]:
    """Return the original immutable image manifest and its version identity."""
    with db.session() as session:
        version = session.scalar(
            select(VersionRow)
            .where(VersionRow.dataset_id == dataset_id)
            .order_by(VersionRow.created_at, VersionRow.id)
        )
        if version is None:
            msg = "Evidence source version not found"
            raise ValidationError(msg)
        return version.id, [FileItem.model_validate(value) for value in version.manifest]
