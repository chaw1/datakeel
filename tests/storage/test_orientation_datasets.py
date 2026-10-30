# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset annotations: imports land upright; legacy batches and splits convert on read."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from datakeel.actions.parameters import ExportParams
from datakeel.core.annotation_models import AnnotationBatch, AnnotationBox, AnnotationRecord
from datakeel.core.image_orientation import ImageGeometry, to_display
from datakeel.core.models import FileItem, JsonDocument, utcnow
from datakeel.core.training_export_models import (
    CocoBox,
    CocoCategory,
    CocoDataset,
    CocoImage,
    TrainingAnnotationImport,
    YoloDataset,
    YoloImage,
)
from datakeel.core.training_models import SplitRequest
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.database import VersionRow
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.training_export import training_export_inputs
from datakeel.storage.training_import import import_training_annotations
from datakeel.storage.training_rows import TrainingSplitRow
from datakeel.storage.training_store import create_split

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

STORED = (60, 40)
MARK = (8.0, 6.0, 26.0, 18.0)
GEOMETRY = ImageGeometry(orientation=6, stored_width=60, stored_height=40)


def _upright() -> tuple[float, float, float, float]:
    corners = [to_display(GEOMETRY, MARK[0], MARK[1]), to_display(GEOMETRY, MARK[2], MARK[3])]
    xs, ys = sorted(c[0] for c in corners), sorted(c[1] for c in corners)
    return (xs[0], ys[0], xs[1], ys[1])


def _version(db: Database, tmp_path: Path) -> tuple[str, str, FileItem]:
    path = tmp_path / "phone.png"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", STORED, (20, 120, 220)).save(path, exif=exif)
    dataset = import_paths(db, "Phone", [path])
    version = list_versions(db, dataset.id)[0]
    with db.session() as session:
        row = session.get(VersionRow, version.id)
        assert row is not None
        return dataset.id, version.id, FileItem.model_validate(row.manifest[0])


def _boxes(record: AnnotationRecord) -> tuple[float, float, float, float]:
    [box] = list(record.boxes or ())
    return (box.x1, box.y1, box.x2, box.y2)


def _batch(db: Database, dataset_id: str, version_id: str) -> AnnotationRecord:
    with db.session() as session:
        rows = session.query(AnnotationBatchRow).filter_by(dataset_id=dataset_id).all()
        assert all(row.coordinate_frame == "display" for row in rows)
        (row,) = rows
        assert row.version_id == version_id
        (record,) = AnnotationBatch.model_validate(row.batch).annotations
        return record


@pytest.mark.parametrize("frame", [None, "stored"])
def test_coco_import_with_stored_size_or_explicit_stored_frame_lands_upright(
    db: Database, tmp_path: Path, frame: str | None
) -> None:
    """COCO declaring the stored 60x40 size is read in stored pixels and converted."""
    dataset_id, version_id, file = _version(db, tmp_path)
    coco = CocoDataset(
        images=(CocoImage(id=1, file_name=file.filename, width=60, height=40),),
        annotations=(CocoBox(id=1, image_id=1, category_id=1, bbox=(8, 6, 18, 12)),),
        categories=(CocoCategory(id=1, name="mark"),),
    )
    request = TrainingAnnotationImport.model_validate(
        {
            "format": "coco",
            "idempotency_key": "coco",
            "coco": coco.model_dump(mode="json"),
            "coordinate_frame": frame,
        }
    )
    import_training_annotations(db, dataset_id, version_id, request)
    record = _batch(db, dataset_id, version_id)
    assert _boxes(record) == pytest.approx(_upright())
    assert (record.image_width, record.image_height) == (40, 60)


def test_yolo_import_is_relative_to_the_upright_image(db: Database, tmp_path: Path) -> None:
    """Normalized YOLO rows describe the upright image even when decoded with the stored size."""
    dataset_id, version_id, file = _version(db, tmp_path)
    x1, y1, x2, y2 = _upright()
    row = f"0 {(x1 + x2) / 80} {(y1 + y2) / 120} {(x2 - x1) / 40} {(y2 - y1) / 60}"
    yolo = YoloDataset(
        names=("mark",), images=(YoloImage(sample_id=file.id, width=60, height=40, labels=row),)
    )
    request = TrainingAnnotationImport(format="yolo", idempotency_key="yolo", yolo=yolo)
    import_training_annotations(db, dataset_id, version_id, request)
    record = _batch(db, dataset_id, version_id)
    assert _boxes(record) == pytest.approx(_upright())
    assert (record.image_width, record.image_height) == (40, 60)


def _stored_record(file: FileItem) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id=file.id,
        annotator_id="legacy",
        labels=("mark",),
        image_width=60,
        image_height=40,
        boxes=(AnnotationBox(category="mark", x1=8, y1=6, x2=26, y2=18),),
    )


def test_legacy_batches_and_frozen_splits_are_read_upright(db: Database, tmp_path: Path) -> None:
    """Pre-upgrade batches and splits stay byte-identical and are converted only when read."""
    dataset_id, version_id, file = _version(db, tmp_path)
    batch = AnnotationBatch(annotations=(_stored_record(file),))
    with db.session() as session:
        session.add(
            AnnotationBatchRow(
                id="legacy-batch",
                dataset_id=dataset_id,
                version_id=version_id,
                idempotency_key="legacy",
                request_digest="legacy",
                batch=batch.model_dump(mode="json"),
                report={},
                created_at=utcnow().timestamp(),
            )
        )
        session.commit()
    split = create_split(db, dataset_id, version_id, SplitRequest(name="after", stratify=False))
    (member,) = split.members
    (record,) = member.annotations
    assert _boxes(record) == pytest.approx(_upright())
    legacy_payload = json.loads(split.model_dump_json()) | {"id": "legacy-split"}
    legacy_payload["members"][0]["annotations"] = [_stored_record(file).model_dump(mode="json")]
    with db.session() as session:
        stored = session.get(TrainingSplitRow, split.id)
        assert stored is not None
        assert stored.coordinate_frame == "display"
        session.add(
            TrainingSplitRow(
                id="legacy-split",
                dataset_id=dataset_id,
                version_id=version_id,
                name="before",
                created_at=utcnow().timestamp(),
                payload=JsonDocument.model_validate(legacy_payload).root,
                samples=stored.samples,
            )
        )
        session.commit()
    for split_id in (split.id, "legacy-split"):
        params = ExportParams(
            dataset_id=dataset_id, version_id=version_id, format="yolo", split_set_id=split_id
        )
        with db.session() as session:
            export = training_export_inputs(session, params, materialize=False)
        (item,) = export.items
        assert _boxes(item.annotation) == pytest.approx(_upright())
    with db.session() as session:
        legacy = session.get(AnnotationBatchRow, "legacy-batch")
        assert legacy is not None
        assert legacy.coordinate_frame is None
        assert AnnotationBatch.model_validate(legacy.batch) == batch
