# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise approved training exports against real local version and annotation stores."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest
from PIL import Image

from datakeel.actions.models import ActionContext
from datakeel.actions.service import prepare_action
from datakeel.core.annotation_models import AnnotationBatch, AnnotationBox, AnnotationRecord
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.errors import BudgetError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.core.training_export_models import (
    CocoDataset,
    TrainingAnnotationImport,
    YoloDataset,
    YoloImage,
)
from datakeel.core.training_models import SplitRequest
from datakeel.storage import training_export
from datakeel.storage.annotation_store import import_annotations
from datakeel.storage.database import data_dir
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.training_import import import_training_annotations
from datakeel.storage.training_store import create_split
from tests.actions.test_service import approve, execute

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datakeel.actions.parameters import ExportParams
    from datakeel.core.training_models import SplitSet
    from datakeel.storage.database import Database


class TrainingFixture(NamedTuple):
    """Carry exact source identities for version-bound action tests."""

    dataset_id: str
    version_id: str
    split: SplitSet
    batch: AnnotationBatch


@pytest.fixture
def training(db: Database, tmp_path: Path) -> TrainingFixture:
    """Generate version files and import a real immutable single-annotator detection batch."""
    paths: list[Path] = []
    for index in range(6):
        path = tmp_path / f"image-{index}.png"
        Image.new("RGB", (100, 80), (index * 20, 10, 50)).save(path)
        paths.append(path)
    dataset = import_paths(db, "Generated training export", paths)
    version = list_versions(db, dataset.id)[0]
    batch = AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(
                sample_id=file.id,
                annotator_id="r",
                labels=("cat",),
                boxes=(AnnotationBox(category="cat", x1=10, y1=20, x2=40, y2=60),),
                image_width=100,
                image_height=80,
            )
            for file in version.manifest
        )
    )
    import_annotations(
        db,
        dataset.id,
        AnnotationImportRequest(version_id=version.id, idempotency_key="initial", batch=batch),
    )
    split = create_split(
        db, dataset.id, version.id, SplitRequest(name="training", avoid_leakage=False)
    )
    return TrainingFixture(dataset.id, version.id, split, batch)


def _params(training: TrainingFixture, **updates: object) -> JsonDocument:
    return JsonDocument.model_validate(
        {
            "dataset_id": training.dataset_id,
            "version_id": training.version_id,
            "format": "coco",
            "split_set_id": training.split.id,
            **updates,
        }
    )


def _contents(path: Path) -> dict[str, bytes]:
    with tarfile.open(path) as archive:
        result: dict[str, bytes] = {}
        for member in archive:
            if member.isfile():
                stream = archive.extractfile(member)
                assert stream is not None
                result[member.name] = stream.read()
        return result


def test_approved_training_exports_are_identical_and_receipts_include_version_split(
    db: Database, training: TrainingFixture
) -> None:
    """Approval binds one version; separate actions produce identical archive bytes."""
    payloads: list[bytes] = []
    for ordinal in range(2):
        plan = prepare_action(
            db, "export_dataset", _params(training, destination=f"training-{ordinal}.tar")
        )
        assert plan.requires_approval
        assert plan.manifest.query.version_ids == [training.version_id]
        approve(db, plan)
        run = execute(db, plan)
        assert run.receipt is not None
        assert any(
            ref.asset_id == training.split.id and ref.version == training.version_id
            for ref in run.receipt.inputs
        )
        assert any(
            ref.asset_id == training.version_id and ref.asset_type == "version"
            for ref in run.receipt.inputs
        )
        payloads.append((data_dir() / "exports" / f"training-{ordinal}.tar").read_bytes())
    assert payloads[0] == payloads[1]


def test_training_export_uses_split_annotations_after_new_annotation_import(
    db: Database, training: TrainingFixture
) -> None:
    """A newer annotation batch never changes the annotations frozen by an existing split."""
    plan = prepare_action(db, "export_dataset", _params(training, destination="frozen.tar"))
    changed = training.batch.model_copy(
        update={
            "annotations": tuple(
                record.model_copy(update={"boxes": (), "labels": ()})
                for record in training.batch.annotations
            )
        }
    )
    import_annotations(
        db,
        training.dataset_id,
        AnnotationImportRequest(
            version_id=training.version_id, idempotency_key="newer", batch=changed
        ),
    )
    approve(db, plan)
    execute(db, plan)
    contents = _contents(data_dir() / "exports/frozen.tar")
    boxes = sum(
        len(CocoDataset.model_validate_json(value).annotations)
        for name, value in contents.items()
        if name.startswith("annotations/")
    )
    assert boxes == 6


def test_modified_split_after_preparation_is_rejected(
    db: Database, training: TrainingFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The action fingerprint binds the frozen split policy and complete annotation payload."""
    plan = prepare_action(db, "export_dataset", _params(training, destination="modified.tar"))
    approve(db, plan)

    def changed_split(_session: Session, _params: ExportParams) -> SplitSet:
        return training.split.model_copy(update={"algorithm_version": "tampered"})

    monkeypatch.setattr(training_export, "_split", changed_split)
    with pytest.raises(ConflictError, match="target state changed"):
        execute(db, plan)
    assert not (data_dir() / "exports/modified.tar").exists()


@pytest.mark.parametrize(
    ("updates", "exception"),
    [
        ({"version_id": None}, ValidationError),
        ({"split_set_id": None}, NotFoundError),
        ({"version_id": "missing"}, NotFoundError),
        ({"annotator_id": "missing"}, ValidationError),
        ({"format": "croissant"}, ValidationError),
    ],
)
def test_training_exports_reject_unbound_or_unavailable_sources(
    db: Database, training: TrainingFixture, updates: dict[str, object], exception: type[Exception]
) -> None:
    """Version, split and annotation choices are checked before persisting an approval plan."""
    with pytest.raises(exception):
        prepare_action(db, "export_dataset", _params(training, **updates))


@pytest.mark.parametrize("format_name", ["coco", "yolo"])
def test_exported_detection_annotations_import_into_existing_version(
    db: Database, training: TrainingFixture, format_name: str
) -> None:
    """Portable COCO and YOLO imports append ordinary version-owned annotation quality history."""
    plan = prepare_action(
        db,
        "export_dataset",
        _params(training, format=format_name, destination=f"{format_name}.tar"),
    )
    approve(db, plan)
    execute(db, plan)
    contents = _contents(data_dir() / "exports" / f"{format_name}.tar")
    if format_name == "coco":
        documents = [
            CocoDataset.model_validate_json(value)
            for name, value in contents.items()
            if name.startswith("annotations/")
        ]
        for ordinal, document in enumerate(documents):
            report = import_training_annotations(
                db,
                training.dataset_id,
                training.version_id,
                TrainingAnnotationImport(
                    format="coco",
                    coco=document,
                    annotator_id="imported",
                    idempotency_key=f"coco-{ordinal}",
                ),
            )
            assert report.sample_count == len(document.images)
    else:
        manifest = json.loads(contents["MANIFEST.json"])
        images = tuple(
            YoloImage(
                sample_id=file["sample_id"],
                width=100,
                height=80,
                labels=contents[
                    str(Path(file["path"].replace("images/", "labels/")).with_suffix(".txt"))
                ].decode(),
            )
            for file in manifest["files"]
        )
        report = import_training_annotations(
            db,
            training.dataset_id,
            training.version_id,
            TrainingAnnotationImport(
                format="yolo",
                yolo=YoloDataset(names=("cat",), images=images),
                annotator_id="imported",
                idempotency_key="yolo",
            ),
        )
        assert report.sample_count == 6


def test_training_export_budget_still_applies(db: Database, training: TrainingFixture) -> None:
    """Training archives use the existing action impact envelope and never bypass object limits."""
    with pytest.raises(BudgetError):
        prepare_action(
            db, "export_dataset", _params(training), context=ActionContext(max_objects=1)
        )


def test_training_export_release_resolves_version_and_exports_frozen_bytes(
    db: Database, training: TrainingFixture
) -> None:
    """A published release can supply the version identity without an explicit version parameter."""
    publication = prepare_action(
        db,
        "publish_release",
        JsonDocument(
            {
                "dataset_id": training.dataset_id,
                "version_id": training.version_id,
                "tag": "v1.0.0",
            }
        ),
    )
    approve(db, publication)
    release_run = execute(db, publication)
    assert release_run.receipt is not None
    release_id = release_run.receipt.outputs[0].asset_id
    plan = prepare_action(
        db,
        "export_dataset",
        _params(training, release_id=release_id, version_id=None, destination="release.tar.gz"),
    )
    assert plan.canonical_params["version_id"] == training.version_id
    approve(db, plan)
    run = execute(db, plan)
    assert run.receipt is not None
    assert any(ref.asset_id == release_id for ref in run.receipt.inputs)
    contents = _contents(data_dir() / "exports/release.tar.gz")
    manifest = json.loads(contents["MANIFEST.json"])
    assert manifest["release_id"] == release_id
    assert manifest["file_count"] == 6
    with pytest.raises(ValidationError, match="release does not match"):
        prepare_action(
            db, "export_dataset", _params(training, release_id=release_id, version_id="other")
        )
