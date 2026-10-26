# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline reconciliation of directory or tar deliveries without platform access."""

import json
import shutil
import tarfile
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError as ModelValidationError

from datakeel.core.delivery_models import (
    DeliveryManifest,
    DeliveryRecords,
    Difference,
    ReconcileReport,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.delivery.checks import (
    annotation_checks,
    hash_checks,
    inventory_checks,
    lineage_checks,
    metadata_checks,
)
from datakeel.delivery.manifest import canonical_hash, safe_relative


@contextmanager
def delivery_directory(source: Path) -> Generator[Path]:
    """Read a directory or safely unpack only regular files from a tar archive."""
    if source.is_dir():
        yield source.resolve()
        return
    with tempfile.TemporaryDirectory(prefix="datakeel-reconcile-") as temporary:
        root = Path(temporary)
        with tarfile.open(source, "r|*") as archive:
            for member in archive:
                _unpack_member(archive, member, root)
        yield root


def _unpack_member(archive: tarfile.TarFile, member: tarfile.TarInfo, root: Path) -> None:
    if member.name in {"MANIFEST.json", "RECORDS.json"}:
        name = Path(member.name)
    else:
        name = Path(safe_relative(member.name))
    if member.isdir():
        (root / name).mkdir(parents=True, exist_ok=True)
        return
    if not member.isfile():
        message = "Delivery archives may contain only regular files and directories"
        raise ValidationError(message)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = archive.extractfile(member)
    if stream is None:
        message = "Unreadable delivery archive member"
        raise ValidationError(message)
    with stream, path.open("xb") as destination:
        shutil.copyfileobj(stream, destination, length=1024 * 1024)


def reconcile(source: Path, manifest_path: Path = Path("MANIFEST.json")) -> ReconcileReport:
    """Verify all six categories using only local delivery content."""
    with delivery_directory(source) as root:
        path = manifest_path if manifest_path.is_absolute() else root / manifest_path
        if path.is_symlink():
            message = "Delivery manifest cannot be a symlink"
            raise ValidationError(message)
        document = JsonDocument.model_validate_json(path.read_bytes())
        manifest = DeliveryManifest.model_validate(document.root)
        for item in manifest.files:
            safe_relative(item.path)
        records, issues = _records(root)
        excluded = {"MANIFEST.json", "RECORDS.json"}
        if path.resolve().is_relative_to(root):
            excluded.add(path.resolve().relative_to(root).as_posix())
        paths = {
            item.relative_to(root).as_posix(): item
            for item in root.rglob("*")
            if (item.is_file() or item.is_symlink())
            and item.relative_to(root).as_posix() not in excluded
        }
        return reconcile_facts(manifest, paths, records, issues, canonical_hash(document.root))


def _records(root: Path) -> tuple[DeliveryRecords, list[Difference]]:
    try:
        path = root / "RECORDS.json"
        content = b"{}" if path.is_symlink() else path.read_bytes()
        return DeliveryRecords.model_validate_json(content), []
    except (OSError, ModelValidationError, ValidationError):
        return DeliveryRecords(files=()), [
            Difference(path="RECORDS.json", reason="missing_or_invalid_records")
        ]


def reconcile_facts(
    manifest: DeliveryManifest,
    paths: dict[str, Path],
    records: DeliveryRecords,
    issues: list[Difference] | None = None,
    received_manifest_hash: str | None = None,
) -> ReconcileReport:
    """Run the same checks against local payloads or platform-materialized objects."""
    by_path = {item.path: item for item in records.files}
    problems = list(issues or [])
    if len(by_path) != len(records.files):
        problems.append(Difference(path="RECORDS.json", reason="duplicate_receipt_records"))
    expected = {item.path for item in manifest.files}
    if len(expected) != len(manifest.files):
        problems.append(Difference(path="MANIFEST.json", reason="duplicate_payload_paths"))
    if set(by_path) != expected:
        problems.append(Difference(path="RECORDS.json", reason="receipt_inventory_mismatch"))
    categories = (
        *inventory_checks(manifest, paths),
        hash_checks(manifest, paths),
        annotation_checks(manifest, by_path),
        metadata_checks(manifest, by_path, problems, records.metadata, received_manifest_hash),
        lineage_checks(manifest, by_path),
    )
    return ReconcileReport(
        release_id=manifest.release_id,
        passed=all(check.passed for check in categories),
        categories=categories,
    )


def report_json(report: ReconcileReport) -> str:
    """Serialize an audit receipt as readable deterministic-key JSON."""
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
