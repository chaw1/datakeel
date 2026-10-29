# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persisted version partitions, frozen annotations, direct signals and native grants."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.data_asset_models import DataAsset, DataAssetDefinition
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import AssetRef, FileItem, utcnow
from datakeel.core.training_models import SplitRequest
from datakeel.storage.annotation_store import import_annotations
from datakeel.storage.data_asset_rows import DataAssetRow
from datakeel.storage.database import DatasetRow, EventRow, VersionRow
from datakeel.storage.objects import digest
from datakeel.storage.training_inputs import load_training_samples
from datakeel.storage.training_rows import TrainingSplitRow
from datakeel.storage.training_store import (
    check_leakage,
    compare_splits,
    create_split,
    get_split,
    list_splits,
    preview_leakage,
    preview_split,
)

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@dataclass(frozen=True)
class TrainingFixture:
    """Keep generated local version ownership and original file facts together."""

    dataset_id: str
    version_id: str
    files: tuple[FileItem, ...]


def _version(db: Database, files: tuple[FileItem, ...]) -> TrainingFixture:
    with db.session() as session:
        dataset = DatasetRow(name="Generated training inputs", files=[])
        session.add(dataset)
        session.flush()
        version = VersionRow(
            dataset_id=dataset.id, manifest=[file.model_dump(mode="json") for file in files]
        )
        session.add(version)
        session.commit()
        return TrainingFixture(dataset.id, version.id, files)


@pytest.fixture
def training(db: Database, tmp_path: Path) -> TrainingFixture:
    """Build thirty distinct local samples with balanced metadata classifications."""
    files: list[FileItem] = []
    for index in range(30):
        path = tmp_path / f"sample-{index}.txt"
        path.write_text(hashlib.sha256(str(index).encode()).hexdigest())
        files.append(
            FileItem(
                id=f"sample-{index:03}",
                filename=path.name,
                path=str(path),
                sha256=digest(path),
                modality="text",
                metadata={
                    "label": f"class-{index % 2}",
                    "split": "train" if index < 20 else "test",
                    "batch": {"id": index // 3},
                },
            )
        )
    return _version(db, tuple(files))


def test_create_freezes_policy_members_and_lineage_with_exact_retry(
    db: Database, training: TrainingFixture
) -> None:
    """A named exact retry preserves the original result without appending another event."""
    request = SplitRequest(name="baseline", group_field="batch.id")
    split = create_split(db, training.dataset_id, training.version_id, request)
    assert split.algorithm_version == "1.3-iterative-text"
    assert split == create_split(db, training.dataset_id, training.version_id, request)
    assert split == get_split(db, training.dataset_id, split.id)
    assert list_splits(db, training.dataset_id, training.version_id) == (split,)
    assert not check_leakage(db, training.dataset_id, split.id).pairs
    assert len(split.members) == 30
    with db.session() as session:
        events = list(session.scalars(select(EventRow)))
        assert len(events) == 1
        assert events[0].payload["inputs"][0]["version"] == training.version_id
    with pytest.raises(ConflictError, match="immutable policy"):
        create_split(
            db, training.dataset_id, training.version_id, request.model_copy(update={"seed": 0})
        )


def test_preview_is_stable_read_only_and_comparison_is_version_scoped(
    db: Database, training: TrainingFixture
) -> None:
    """Preview writes no rows; stored comparisons list exactly changed assignments."""
    request = SplitRequest(name="preview")
    preview = preview_split(db, training.dataset_id, training.version_id, request)
    assert preview == preview_split(db, training.dataset_id, training.version_id, request)
    assert not list_splits(db, training.dataset_id, training.version_id)
    left = create_split(db, training.dataset_id, training.version_id, request)
    right = create_split(
        db,
        training.dataset_id,
        training.version_id,
        request.model_copy(update={"name": "second", "seed": 3}),
    )
    comparison = compare_splits(db, training.dataset_id, left.id, right.id)
    assert comparison.changed_sample_ids
    other = _version(db, training.files)
    third = create_split(db, other.dataset_id, other.version_id, request)
    with pytest.raises(NotFoundError, match="dataset"):
        get_split(db, training.dataset_id, third.id)
    with pytest.raises(NotFoundError, match="Version"):
        list_splits(db, training.dataset_id, other.version_id)
    with pytest.raises(NotFoundError, match="dataset"):
        compare_splits(db, training.dataset_id, left.id, third.id)


def test_stored_splits_and_bound_versions_reject_direct_sql_mutation(
    db: Database, training: TrainingFixture
) -> None:
    """Database constraints preserve assignment and manifest immutability below services."""
    split = create_split(db, training.dataset_id, training.version_id, SplitRequest(name="sealed"))
    for statement, identity in (
        ("UPDATE training_splits SET name = 'changed' WHERE id = :id", split.id),
        ("DELETE FROM training_splits WHERE id = :id", split.id),
        ("UPDATE versions SET manifest = '[]' WHERE id = :id", training.version_id),
    ):
        with db.session() as session, pytest.raises(DBAPIError, match="immutable"):
            session.execute(text(statement), {"id": identity})


def test_split_freezes_annotation_revision_and_new_policy_reads_latest(
    db: Database, training: TrainingFixture
) -> None:
    """Later annotation imports cannot alter old split labels or frozen export annotations."""
    sample_id = training.files[0].id
    for index, label in enumerate(("before", "after")):
        import_annotations(
            db,
            training.dataset_id,
            AnnotationImportRequest(
                version_id=training.version_id,
                idempotency_key=str(index),
                batch=AnnotationBatch(
                    annotations=(
                        AnnotationRecord(
                            sample_id=sample_id, annotator_id="reviewer", labels=(label,)
                        ),
                    )
                ),
            ),
        )
        split = create_split(db, training.dataset_id, training.version_id, SplitRequest(name=label))
        assert next(member.labels for member in split.members if member.sample_id == sample_id) == (
            label,
        )
    first = list_splits(db, training.dataset_id, training.version_id)[0]
    assert next(
        member.annotations[0].labels for member in first.members if member.sample_id == sample_id
    ) == ("before",)


def test_directory_preview_keeps_assignments_and_checks_text_near_duplicates(
    db: Database, tmp_path: Path
) -> None:
    """Formatting variants yield simhash evidence while an unrelated control stays clean."""
    files: list[FileItem] = []
    texts = (
        "A brief description, of a brown fox!",
        " a BRIEF description of a brown FOX ",
        "Computer kernels manage virtual memory",
        "A brief description, of a brown fox!",
    )
    for index, content in enumerate(texts):
        path = tmp_path / f"text-{index}.txt"
        path.write_text(content)
        files.append(
            FileItem(
                id=str(index),
                path=str(path),
                filename=path.name,
                modality="text",
                sha256=digest(path),
                metadata={"split": "train" if index == 0 else "test"},
            )
        )
    fixture = _version(db, tuple(files))
    request = SplitRequest(name="external", source="directory")
    report = preview_leakage(db, fixture.dataset_id, fixture.version_id, request)
    assert [(pair.kind, pair.left_id, pair.right_id, pair.distance) for pair in report.pairs] == [
        ("exact", "0", "3", 0),
        ("text", "0", "1", 0),
        ("text", "0", "3", 0),
    ]
    assert report.checked_signals == ("exact", "image", "text", "group")
    samples = load_training_samples(db, fixture.dataset_id, fixture.version_id)
    assert all(sample.text_hash is not None for sample in samples)
    assert all(sample.file.sha256 == digest(Path(sample.file.path)) for sample in samples)
    split = create_split(db, fixture.dataset_id, fixture.version_id, request)
    assert check_leakage(db, fixture.dataset_id, split.id).pairs == report.pairs


def test_image_resize_and_compression_are_recalled_with_clean_control(
    db: Database, tmp_path: Path
) -> None:
    """Resampled/recompressed pixels retain dHash while independent generated noise stays clean."""
    generator = np.random.default_rng(42)
    original = Image.fromarray(generator.integers(0, 256, (96, 96, 3), dtype=np.uint8))
    clean = Image.fromarray(generator.integers(0, 256, (96, 96, 3), dtype=np.uint8))
    paths = (tmp_path / "original.png", tmp_path / "changed.jpg", tmp_path / "clean.png")
    original.save(paths[0])
    original.resize((144, 144)).save(paths[1], quality=90)
    clean.save(paths[2])
    files = tuple(
        FileItem(
            id=str(index),
            path=str(path),
            filename=path.name,
            modality="image",
            sha256=digest(path),
            metadata={"split": "train" if index == 0 else "val"},
        )
        for index, path in enumerate(paths)
    )
    fixture = _version(db, files)
    report = preview_leakage(
        db, fixture.dataset_id, fixture.version_id, SplitRequest(name="images", source="directory")
    )
    assert [(pair.kind, pair.left_id, pair.right_id) for pair in report.pairs] == [
        ("image", "0", "1")
    ]


def test_protected_source_is_rejected_before_content_reads(
    db: Database, training: TrainingFixture
) -> None:
    """Every generated, preview, list and saved read entrance enforces native grants."""
    request = SplitRequest(name="public-first")
    split = create_split(db, training.dataset_id, training.version_id, request)
    asset = DataAsset(
        id="protected",
        revision=1,
        definition=DataAssetDefinition(
            target=AssetRef(asset_id=training.dataset_id, version=training.version_id),
            name="Protected source",
            owner="owner",
            classification="restricted",
        ),
        status="published",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    with db.session() as session:
        session.add(DataAssetRow(id=asset.id, payload=asset.model_dump(mode="json")))
        session.commit()
    operations = (
        lambda: preview_split(db, training.dataset_id, training.version_id, request),
        lambda: create_split(db, training.dataset_id, training.version_id, request),
        lambda: list_splits(db, training.dataset_id, training.version_id),
        lambda: get_split(db, training.dataset_id, split.id),
        lambda: check_leakage(db, training.dataset_id, split.id),
    )
    for operation in operations:
        with pytest.raises(AuthorizationError, match="grant"):
            operation()


def test_training_content_validation_rejects_hash_drift_and_invalid_text(
    db: Database, training: TrainingFixture, tmp_path: Path
) -> None:
    """Actual bytes are checked before a split can claim an immutable content identity."""
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"\xff\xfe")
    invalid = _version(
        db, (FileItem(id="invalid", path=str(path), filename=path.name, modality="text"),)
    )
    with pytest.raises(ValidationError, match="UTF-8"):
        load_training_samples(db, invalid.dataset_id, invalid.version_id)
    first = training.files[0]
    Path(first.path).write_text("changed content")
    with pytest.raises(ConflictError, match="version hash"):
        load_training_samples(db, training.dataset_id, training.version_id)


def test_external_directory_fallback_recognizes_test_before_object_materialization(
    db: Database, tmp_path: Path
) -> None:
    """An ordinary imported path under test/ retains its external partition assignment."""
    path = tmp_path / "test" / "sample.txt"
    path.parent.mkdir()
    path.write_text("Generated external partition content")
    fixture = _version(
        db, (FileItem(id="test-sample", path=str(path), filename=path.name, modality="text"),)
    )
    preview = preview_split(
        db, fixture.dataset_id, fixture.version_id, SplitRequest(name="path", source="directory")
    )
    assert preview.members[0].split == "test"


def test_flat_color_dhash_collision_requires_color_confirmation(
    db: Database, tmp_path: Path
) -> None:
    """Flat red recompression matches; blue, gray and white controls do not falsely match."""
    colors = ("red", "red", "blue", "gray", "white")
    files: list[FileItem] = []
    for index, color in enumerate(colors):
        path = tmp_path / (f"flat-{index}.jpg" if index == 1 else f"flat-{index}.png")
        Image.new("RGB", (80, 80), color).save(path)
        files.append(
            FileItem(
                id=str(index),
                path=str(path),
                filename=path.name,
                sha256=digest(path),
                modality="image",
                metadata={"split": "train" if index == 0 else "test"},
            )
        )
    fixture = _version(db, tuple(files))
    report = preview_leakage(
        db, fixture.dataset_id, fixture.version_id, SplitRequest(name="flat", source="directory")
    )
    assert [(pair.kind, pair.left_id, pair.right_id) for pair in report.pairs] == [
        ("image", "0", "1")
    ]


def test_corrupt_training_image_fails_before_saving_split(db: Database, tmp_path: Path) -> None:
    """An undecodable image produces a typed failure instead of silently missing leakage."""
    path = tmp_path / "corrupt.png"
    path.write_bytes(b"invalid image")
    fixture = _version(
        db, (FileItem(id="corrupt", path=str(path), filename=path.name, modality="image"),)
    )
    with pytest.raises(ValidationError, match="decoded"):
        create_split(db, fixture.dataset_id, fixture.version_id, SplitRequest(name="corrupt"))
    assert not list_splits(db, fixture.dataset_id, fixture.version_id)


def test_existing_algorithm_snapshot_is_returned_without_rewriting(
    db: Database, training: TrainingFixture
) -> None:
    """New algorithms keep older immutable names and snapshots readable."""
    request = SplitRequest(name="legacy")
    preview = preview_split(db, training.dataset_id, training.version_id, request)
    legacy = preview.model_copy(
        update={"id": "legacy-split", "algorithm_version": "1.2-primary-no-text"}
    )
    old_samples = tuple(
        sample.model_copy(update={"file": sample.file.model_copy(update={"path": "unavailable"})})
        for sample in load_training_samples(db, training.dataset_id, training.version_id)
    )
    with db.session() as session:
        session.add(
            TrainingSplitRow(
                id=legacy.id,
                dataset_id=training.dataset_id,
                version_id=training.version_id,
                name=request.name,
                created_at=legacy.created_at.timestamp(),
                payload=legacy.model_dump(mode="json"),
                samples=[
                    sample.model_dump(mode="json", exclude={"text_hash"}) for sample in old_samples
                ],
            )
        )
        session.commit()
    assert create_split(db, training.dataset_id, training.version_id, request) == legacy
    assert get_split(db, training.dataset_id, legacy.id) == legacy
    report = check_leakage(db, training.dataset_id, legacy.id)
    assert report.checked_signals == ("exact", "image", "group")
    assert not report.pairs
    assert preview.id != legacy.id
