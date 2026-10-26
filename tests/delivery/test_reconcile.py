# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Delivery fault injection exercises independent receipt-side verification."""

import io
import json
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from datakeel.core.delivery_models import DeliveryManifest
from datakeel.core.errors import ValidationError
from datakeel.delivery.manifest import manifest_hash, safe_relative, validate_manifest
from datakeel.delivery.reconcile import reconcile

if TYPE_CHECKING:
    from pydantic import JsonValue


def test_original_delivery_passes_all_six_categories(package: Path) -> None:
    """An unchanged delivery passes every independently named check."""
    report = reconcile(package)
    assert report.passed
    assert len(report.categories) == 6
    assert all(item.passed and not item.differences for item in report.categories)
    validate_manifest(
        DeliveryManifest.model_validate_json((package / "MANIFEST.json").read_bytes())
    )


@pytest.mark.parametrize(
    ("fault", "category"),
    [
        ("missing", "file_count"),
        ("extra", "file_count"),
        ("byte", "hashes"),
        ("truncated", "bytes"),
        ("metadata", "metadata"),
        ("lineage", "lineage"),
        ("annotations", "annotations"),
    ],
)
def test_fault_is_reported_in_its_category(package: Path, fault: str, category: str) -> None:
    """Each specified injected corruption produces differences in its own category."""
    payload = package / "files/0.txt"
    if fault == "missing":
        payload.unlink()
    elif fault == "extra":
        (package / "extra.txt").write_text("extra")
    elif fault == "byte":
        payload.write_bytes(b"X" + payload.read_bytes()[1:])
    elif fault == "truncated":
        payload.write_bytes(payload.read_bytes()[:-1])
    elif fault == "lineage":
        document = json.loads((package / "MANIFEST.json").read_text())
        document["lineage"] = []
        (package / "MANIFEST.json").write_text(json.dumps(document))
    else:
        document = json.loads((package / "RECORDS.json").read_text())
        if fault == "metadata":
            document["files"][0]["metadata"]["license"] = "changed"
        else:
            document["files"][0]["annotation_count"] = 99
        (package / "RECORDS.json").write_text(json.dumps(document))
    report = reconcile(package)
    failed = next(item for item in report.categories if item.name == category)
    assert not report.passed
    assert not failed.passed
    assert failed.differences


def test_tar_delivery_passes_and_has_identical_checks(package: Path, tmp_path: Path) -> None:
    """Receipt verification also accepts the standalone tar delivery format."""
    archive = tmp_path / "delivery.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                stream.add(path, arcname=path.relative_to(package).as_posix())
    assert reconcile(archive).passed


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a\\b", "a/./b", "x:y", ""])
def test_unsafe_manifest_paths_are_rejected(name: str) -> None:
    """Never open arbitrary recipient filesystem locations from a manifest."""
    with pytest.raises(ValidationError, match="Unsafe"):
        safe_relative(name)


@pytest.mark.parametrize("kind", ["traversal", "symlink", "duplicate"])
def test_unsafe_archive_members_are_rejected(tmp_path: Path, kind: str) -> None:
    """Reject traversal, links and duplicated archive members before reconciliation."""
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as stream:
        member = tarfile.TarInfo("../escape" if kind == "traversal" else "files/item")
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
        stream.addfile(member, io.BytesIO())
        if kind == "duplicate":
            stream.addfile(member, io.BytesIO())
    with pytest.raises((ValidationError, FileExistsError)):
        reconcile(archive)


def test_missing_records_fail_metadata_annotations_and_lineage(package: Path) -> None:
    """Payload checks can pass even when the independent receipt records are missing."""
    (package / "RECORDS.json").unlink()
    report = reconcile(package)
    assert [item.name for item in report.categories if not item.passed] == [
        "annotations",
        "metadata",
        "lineage",
    ]


def test_symlink_payload_does_not_read_outside_package(package: Path, tmp_path: Path) -> None:
    """A symlink cannot masquerade as a verified regular payload."""
    payload = package / "files/0.txt"
    outside = tmp_path / "outside"
    outside.write_bytes(payload.read_bytes())
    payload.unlink()
    payload.symlink_to(outside)
    report = reconcile(package)
    assert not next(item for item in report.categories if item.name == "hashes").passed


def test_manifest_checksum_detects_expected_metadata_tampering(package: Path) -> None:
    """Changing the expected document cannot silently redefine successful delivery."""
    path = package / "MANIFEST.json"
    document = json.loads(path.read_bytes())
    document["tag"] = "v9.9.9"
    path.write_text(json.dumps(document))
    report = reconcile(package)
    check = next(item for item in report.categories if item.name == "metadata")
    assert any(item.reason == "manifest_sha256" for item in check.differences)


def test_checked_in_schema_matches_runtime_contract() -> None:
    """The public schema is exactly the validator contract used during export."""
    document = cast(
        "dict[str, JsonValue]",
        json.loads(Path("contracts/delivery-manifest.schema.json").read_text()),
    )
    document.pop("$schema")
    assert document == DeliveryManifest.model_json_schema()


def test_metadata_type_corruption_is_detected(package: Path) -> None:
    """A boolean must not impersonate a numeric metadata value through Python equality."""
    manifest_path = package / "MANIFEST.json"
    manifest = DeliveryManifest.model_validate_json(manifest_path.read_bytes())
    files = list(manifest.files)
    files[0] = files[0].model_copy(update={"metadata": {**files[0].metadata, "rating": 1}})
    manifest = manifest.model_copy(update={"files": tuple(files)})
    manifest = manifest.model_copy(update={"manifest_sha256": manifest_hash(manifest)})
    manifest_path.write_text(manifest.model_dump_json())
    record_path = package / "RECORDS.json"
    records = json.loads(record_path.read_text())
    records["files"][0]["metadata"]["rating"] = True
    record_path.write_text(json.dumps(records))
    result = reconcile(package)
    metadata = next(item for item in result.categories if item.name == "metadata")
    assert not metadata.passed
    assert any(item.reason == "metadata:rating" for item in metadata.differences)


def test_custom_manifest_inside_delivery_is_not_counted_as_payload(package: Path) -> None:
    """A selected manifest can have an arbitrary relative name without becoming an extra file."""
    (package / "MANIFEST.json").rename(package / "custom-manifest.json")
    assert reconcile(package, Path("custom-manifest.json")).passed


def test_manifest_default_field_removal_does_not_hide_checksum_change(package: Path) -> None:
    """Hash received JSON before model defaults can recreate a removed manifest field."""
    path = package / "MANIFEST.json"
    document = json.loads(path.read_text())
    del document["metadata"]
    path.write_text(json.dumps(document))
    report = reconcile(package)
    metadata = next(item for item in report.categories if item.name == "metadata")
    assert not metadata.passed
    assert any(item.reason == "manifest_sha256" for item in metadata.differences)
