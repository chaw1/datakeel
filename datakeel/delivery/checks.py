# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Six independent receipt checks over expected and received delivery facts."""

import json
from pathlib import Path

from pydantic import JsonValue

from datakeel.core.delivery_models import (
    CheckName,
    CheckResult,
    DeliveryManifest,
    DeliveryRecord,
    Difference,
)
from datakeel.core.release_models import annotation_statistics
from datakeel.delivery.manifest import file_hash, manifest_hash, safe_relative


def result(name: CheckName, differences: list[Difference]) -> CheckResult:
    """Freeze one category after collecting its detailed differences."""
    return CheckResult(name=name, passed=not differences, differences=tuple(differences))


def inventory_checks(manifest: DeliveryManifest, paths: dict[str, Path]) -> list[CheckResult]:
    """Compare both registered and actual inventory totals, including extra files."""
    expected = {item.path for item in manifest.files}
    actual = set(paths)
    differences = [
        Difference(path=path, reason="missing_file", expected=True, actual=False)
        for path in sorted(expected - actual)
    ] + [
        Difference(path=path, reason="extra_file", expected=False, actual=True)
        for path in sorted(actual - expected)
    ]
    if manifest.file_count != len(paths) or manifest.file_count != len(manifest.files):
        differences.append(
            Difference(
                path=".", reason="file_count", expected=manifest.file_count, actual=len(paths)
            )
        )
    byte_differences: list[Difference] = []
    for item in manifest.files:
        size = _size(paths.get(item.path))
        if size != item.size:
            byte_differences.append(
                Difference(path=item.path, reason="file_bytes", expected=item.size, actual=size)
            )
    total = sum(_size(path) or 0 for path in paths.values())
    if total != manifest.total_bytes or sum(item.size for item in manifest.files) != total:
        byte_differences.append(
            Difference(path=".", reason="total_bytes", expected=manifest.total_bytes, actual=total)
        )
    return [result("file_count", differences), result("bytes", byte_differences)]


def _size(path: Path | None) -> int | None:
    return path.stat().st_size if path and path.is_file() and not path.is_symlink() else None


def hash_checks(manifest: DeliveryManifest, paths: dict[str, Path]) -> CheckResult:
    """Check every received payload against its pinned content checksum."""
    differences: list[Difference] = []
    for item in manifest.files:
        path = paths.get(item.path)
        actual = file_hash(path) if path and _size(path) is not None else None
        if actual != item.sha256:
            differences.append(
                Difference(path=item.path, reason="sha256", expected=item.sha256, actual=actual)
            )
    return result("hashes", differences)


def annotation_checks(
    manifest: DeliveryManifest, records: dict[str, DeliveryRecord]
) -> CheckResult:
    """Compare registered annotation and label statistics to independent receipt records."""
    differences: list[Difference] = []
    for item in manifest.files:
        record = records.get(item.path)
        for name in ("annotation_count", "label_count"):
            actual = getattr(record, name) if record else None
            expected = getattr(item, name)
            if actual != expected:
                differences.append(
                    Difference(path=item.path, reason=name, expected=expected, actual=actual)
                )
        if record:
            differences.extend(_annotation_values(record))
    return result("annotations", differences)


def _annotation_values(record: DeliveryRecord) -> list[Difference]:
    differences: list[Difference] = []
    annotations, labels = annotation_statistics(record.metadata)
    for keys, actual, expected in (
        (("annotations", "annotation", "annotation_count"), annotations, record.annotation_count),
        (("labels", "label", "label_count"), labels, record.label_count),
    ):
        if any(key in record.metadata for key in keys) and actual != expected:
            differences.append(
                Difference(path=record.path, reason=keys[0], expected=expected, actual=actual)
            )
    return differences


def metadata_checks(
    manifest: DeliveryManifest,
    records: dict[str, DeliveryRecord],
    issues: list[Difference],
    received_metadata: dict[str, JsonValue],
    received_manifest_hash: str | None = None,
) -> CheckResult:
    """Compare public metadata values, required fields and manifest integrity."""
    differences = issues.copy()
    actual_manifest_hash = received_manifest_hash or manifest_hash(manifest)
    if actual_manifest_hash != manifest.manifest_sha256:
        differences.append(Difference(path="MANIFEST.json", reason="manifest_sha256"))
    differences.extend(
        _metadata_values(".", manifest.metadata, received_metadata, manifest.required_metadata)
    )
    for item in manifest.files:
        safe_relative(item.path)
        record = records.get(item.path)
        actual = record.metadata if record else {}
        differences.extend(
            _metadata_values(item.path, item.metadata, actual, item.required_metadata)
        )
    return result("metadata", differences)


def _metadata_values(
    path: str,
    expected: dict[str, JsonValue],
    actual: dict[str, JsonValue],
    required: tuple[str, ...],
) -> list[Difference]:
    return [
        Difference(
            path=path, reason=f"metadata:{key}", expected=expected.get(key), actual=actual.get(key)
        )
        for key in sorted(set(expected) | set(actual) | set(required))
        if key not in actual
        or key not in expected
        or json.dumps(expected.get(key), sort_keys=True, ensure_ascii=False)
        != json.dumps(actual.get(key), sort_keys=True, ensure_ascii=False)
    ]


def lineage_checks(manifest: DeliveryManifest, records: dict[str, DeliveryRecord]) -> CheckResult:
    """Ensure every source and ancestry reference resolves inside the delivery."""
    known = {item.version_id for item in manifest.lineage if item.dataset_id == manifest.dataset_id}
    differences: list[Difference] = []
    if len(known) != len(manifest.lineage):
        differences.append(Difference(path="MANIFEST.json", reason="duplicate_or_foreign_lineage"))
    if manifest.source_version not in known:
        differences.append(Difference(path="MANIFEST.json", reason="unknown_source_version"))
    for item in manifest.files:
        record = records.get(item.path)
        refs = set(item.lineage_refs)
        if not refs or item.source_version not in refs or not refs <= known:
            differences.append(Difference(path=item.path, reason="unresolved_lineage_reference"))
        if not record or (
            record.source_version != item.source_version
            or set(record.lineage_refs) != refs
            or record.source_version not in known
        ):
            differences.append(Difference(path=item.path, reason="receipt_lineage_mismatch"))
    return result("lineage", differences)
