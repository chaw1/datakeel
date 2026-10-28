# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated delivery contracts independent of any application service."""

import hashlib
from pathlib import Path

import pytest

from datakeel.core.delivery_models import (
    DeliveryFile,
    DeliveryLineage,
    DeliveryManifest,
    DeliveryRecord,
    DeliveryRecords,
)
from datakeel.delivery.manifest import manifest_hash


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """Create a two-file release with independent receipt-side facts."""
    root = tmp_path / "delivery"
    (root / "files").mkdir(parents=True)
    entries: list[DeliveryFile] = []
    records: list[DeliveryRecord] = []
    for ordinal, payload in enumerate((b"first payload\n", b"second payload\n")):
        relative = f"files/{ordinal}.txt"
        (root / relative).write_bytes(payload)
        entry = DeliveryFile(
            path=relative,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            media_type="text/plain",
            source_version="version-one",
            lineage_refs=("version-one",),
            annotation_count=1,
            label_count=2,
            required_metadata=("license",),
            metadata={"license": "CC0-1.0", "annotations": ["box"], "labels": ["a", "b"]},
        )
        entries.append(entry)
        records.append(
            DeliveryRecord(
                path=relative,
                metadata=entry.metadata,
                annotation_count=1,
                label_count=2,
                source_version=entry.source_version,
                lineage_refs=entry.lineage_refs,
            )
        )
    manifest = DeliveryManifest(
        release_id="release-one",
        tag="v1.0.0",
        dataset_id="dataset-one",
        source_version="version-one",
        files=tuple(entries),
        lineage=(DeliveryLineage(version_id="version-one", dataset_id="dataset-one"),),
        file_count=2,
        total_bytes=sum(item.size for item in entries),
        manifest_sha256="0" * 64,
    )
    manifest = manifest.model_copy(update={"manifest_sha256": manifest_hash(manifest)})
    (root / "MANIFEST.json").write_text(manifest.model_dump_json(indent=2))
    (root / "RECORDS.json").write_text(
        DeliveryRecords(files=tuple(records)).model_dump_json(indent=2)
    )
    return root
