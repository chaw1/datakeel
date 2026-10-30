# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""v0.18.0 records read upright: file lists, version manifests and evidence samples."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PIL import Image

from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence.generator import generate_samples
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.dataset_service import import_paths, list_files, list_versions
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest
from datakeel.storage.evidence_queries import get_evidence
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute
from tests.evidence.helpers import stored_frame_extractors

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database

_GEOMETRY = ("width", "height", "stored_width", "stored_height", "orientation")
UPRIGHT = {"width": 40, "height": 60, "stored_width": 60, "stored_height": 40, "orientation": 6}


def _as_v0_18(metadata: dict[str, object]) -> None:
    """v0.18.0 recorded the stored size as width/height and nothing else."""
    for name in _GEOMETRY:
        metadata.pop(name, None)
    metadata.update(width=60, height=40)


def _legacy_dataset(db: Database, tmp_path: Path) -> tuple[str, str]:
    path = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (60, 40), (20, 120, 220)).save(path, exif=exif)
    dataset = import_paths(db, "Phone", [path])
    version = list_versions(db, dataset.id)[0]
    with db.session() as session:
        row = session.get(DatasetRow, dataset.id)
        stored = session.get(VersionRow, version.id)
        assert row is not None
        assert stored is not None
        files, manifest = copy.deepcopy(row.files), copy.deepcopy(stored.manifest)
        for item in (*files, *manifest):
            _as_v0_18(item["metadata"])
        row.files, stored.manifest = files, manifest
        session.commit()
    return dataset.id, version.id


def _raw(db: Database, dataset_id: str, version_id: str) -> tuple[object, object]:
    with db.session() as session:
        row = session.get(DatasetRow, dataset_id)
        stored = session.get(VersionRow, version_id)
        assert row is not None
        assert stored is not None
        return copy.deepcopy(row.files), copy.deepcopy(stored.manifest)


def test_v0_18_file_list_reads_upright_size_stored_size_and_orientation(
    db: Database, tmp_path: Path
) -> None:
    """A 60x40 stored, EXIF 6 phone photo lists as 40x60 without touching the manifest."""
    dataset_id, version_id = _legacy_dataset(db, tmp_path)
    before = _raw(db, dataset_id, version_id)
    listed = [
        *list_files(db, dataset_id),
        *list_files(db, dataset_id, version_id),
        *list_versions(db, dataset_id)[0].manifest,
    ]
    assert [{name: item.metadata.get(name) for name in _GEOMETRY} for item in listed] == [
        UPRIGHT
    ] * 3
    assert _raw(db, dataset_id, version_id) == before, "the immutable manifest is not rewritten"


def test_v0_18_evidence_sample_reports_the_upright_size(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stale stored-size facts from a v0.18.0 extraction do not leak into the sample's size."""
    directory = tmp_path / "samples"
    generate_samples(directory, samples=10)
    image = directory / "train/scene-0000/image.png"
    with Image.open(image) as source:
        stored = source.copy()
    exif = Image.Exif()
    exif[274] = 6
    stored.save(image, exif=exif)
    dataset_id = import_evidence_samples(db, "legacy evidence", directory).id
    version_id, files = source_manifest(db, dataset_id)
    rotated = next(item.id for item in files if item.filename.startswith("train/scene-0000/"))
    with monkeypatch.context() as legacy:
        stored_frame_extractors(legacy)
        queue = DatabaseQueue(db)
        queue.submit(dataset_id, "v0.18.0", evidence_pipeline())
        lease = queue.claim()
        assert lease is not None
        assert execute(queue, lease)
    sample = get_evidence(db, rotated, version_id)
    assert (sample.image_width, sample.image_height) == (stored.height, stored.width)
    assert stored.width != stored.height
