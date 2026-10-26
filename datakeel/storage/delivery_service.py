# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export frozen releases and archive reconciliation of actual backend objects."""

import hashlib
import mimetypes
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select

from datakeel.core.delivery_models import (
    DeliveryFile,
    DeliveryLineage,
    DeliveryManifest,
    DeliveryRecord,
    DeliveryRecords,
    ReconcileReport,
)
from datakeel.core.errors import ConflictError
from datakeel.core.release_models import ReleaseView
from datakeel.delivery.manifest import file_hash, manifest_hash, safe_relative, validate_manifest
from datakeel.delivery.reconcile import reconcile
from datakeel.storage.database import Database
from datakeel.storage.delivery_rows import ReconciliationRow
from datakeel.storage.objects import ObjectStore, fresh_object, object_store
from datakeel.storage.release_service import iter_release_entries, require_release

_FIRST_PRINTABLE = 32
_MAX_BASENAME = 200
_NAME_PREFIX = 160
_SUFFIX_LIMIT = 20


def _payload_path(ordinal: int, filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(character for character in name if ord(character) >= _FIRST_PRINTABLE)
    name = quote(name if name not in {"", ".", ".."} else "file", safe=" ._-")
    if len(name) > _MAX_BASENAME:
        suffix = quote(Path(filename).suffix, safe=".")[:_SUFFIX_LIMIT]
        checksum = hashlib.sha256(filename.encode()).hexdigest()[:12]
        name = f"{name[:_NAME_PREFIX]}-{checksum}{suffix}"
    relative = f"files/{ordinal:08d}/{name}"
    return str(safe_relative(relative))


def _manifest(release: ReleaseView, files: list[DeliveryFile]) -> DeliveryManifest:
    manifest = DeliveryManifest(
        release_id=release.id,
        tag=release.tag,
        dataset_id=release.dataset_id,
        source_version=release.version_id,
        metadata=release.metadata,
        required_metadata=tuple(sorted(release.metadata)),
        files=tuple(files),
        lineage=(DeliveryLineage(version_id=release.version_id, dataset_id=release.dataset_id),),
        file_count=len(files),
        total_bytes=sum(item.size for item in files),
        manifest_sha256="0" * 64,
    )
    result = manifest.model_copy(update={"manifest_sha256": manifest_hash(manifest)})
    validate_manifest(result)
    return result


def _write_delivery(db: Database, identifier: str, directory: Path, *, strict: bool) -> None:
    files: list[DeliveryFile] = []
    records: list[DeliveryRecord] = []
    store = object_store()
    with db.session() as session:
        release = require_release(session, identifier)
        for ordinal, entry in enumerate(iter_release_entries(session, identifier)):
            item = entry.file
            relative = _payload_path(ordinal, item.filename)
            record = DeliveryFile(
                path=relative,
                size=item.size,
                sha256=item.sha256,
                media_type=mimetypes.guess_type(item.filename)[0] or "application/octet-stream",
                source_version=item.source_version,
                lineage_refs=item.lineage_refs,
                annotation_count=item.annotation_count,
                label_count=item.label_count,
                required_metadata=tuple(sorted(item.metadata)),
                metadata=item.metadata,
            )
            files.append(record)
            records.append(
                DeliveryRecord.model_validate(
                    record.model_dump(exclude={"size", "sha256", "media_type", "required_metadata"})
                )
            )
            _copy_payload(store, entry.object_key, directory / relative, record, strict=strict)
    manifest = _manifest(release, files)
    (directory / "MANIFEST.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (directory / "RECORDS.json").write_text(
        DeliveryRecords(metadata=release.metadata, files=tuple(records)).model_dump_json(indent=2),
        encoding="utf-8",
    )


def _copy_payload(
    store: ObjectStore,
    key: str,
    destination: Path,
    record: DeliveryFile,
    *,
    strict: bool,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with fresh_object(store, key) as source:
            shutil.copyfile(source, destination)
    except FileNotFoundError:
        if strict:
            raise
        return
    if strict and (
        destination.stat().st_size != record.size or file_hash(destination) != record.sha256
    ):
        message = "Stored content differs from the immutable release; export refused"
        raise ConflictError(message)


def export_release(db: Database, identifier: str, output: Path) -> Path:
    """Atomically create a new directory or tar delivery, refusing to overwrite receipts."""
    if output.exists():
        message = "Delivery output already exists"
        raise ConflictError(message)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".datakeel-delivery-", dir=output.parent) as temporary:
        directory = Path(temporary) / "package"
        directory.mkdir()
        _write_delivery(db, identifier, directory, strict=True)
        if output.name.endswith((".tar", ".tar.gz", ".tgz")):
            archive = Path(temporary) / "delivery.tar"
            mode = "w" if output.suffix == ".tar" else "w:gz"
            with tarfile.open(archive, mode) as stream:
                for path in sorted(directory.rglob("*")):
                    if path.is_file():
                        stream.add(
                            path, arcname=path.relative_to(directory).as_posix(), recursive=False
                        )
            os.link(archive, output)
        else:
            directory.rename(output)
    return output


def reconcile_release(db: Database, identifier: str) -> ReconcileReport:
    """Verify actual backend objects with the identical offline engine and archive the receipt."""
    with tempfile.TemporaryDirectory(prefix="datakeel-release-check-") as temporary:
        directory = Path(temporary)
        _write_delivery(db, identifier, directory, strict=False)
        report = reconcile(directory)
    with db.session() as session:
        session.add(
            ReconciliationRow(
                id=report.id,
                release_id=identifier,
                created_at=report.created_at,
                report=report.model_dump(mode="json"),
            )
        )
        session.commit()
    return report


def list_reconciliations(db: Database, identifier: str) -> list[ReconcileReport]:
    """Return archived receipts for one release in chronological order."""
    with db.session() as session:
        require_release(session, identifier)
        return [
            ReconcileReport.model_validate(row.report)
            for row in session.scalars(
                select(ReconciliationRow)
                .where(ReconciliationRow.release_id == identifier)
                .order_by(ReconciliationRow.created_at, ReconciliationRow.id)
            )
        ]
