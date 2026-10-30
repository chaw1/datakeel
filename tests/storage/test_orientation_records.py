# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""EXIF-oriented images: upright geometry at import, upright pixels, legacy and imported frames."""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image, ImageOps

from datakeel.api.app import create_app
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.image_orientation import ImageGeometry, to_display
from datakeel.core.models import FileItem, utcnow
from datakeel.core.production_models import AnnotationRevision
from datakeel.core.workbench_models import WorkbenchTask
from datakeel.storage.database import VersionRow
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.image_geometry import file_geometry
from datakeel.storage.production_queries import list_tasks
from datakeel.storage.production_rows import ProductionRevisionRow, ProductionTaskRow
from tests.asgi_client import TestClient
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

STORED = (60, 40)
MARK = (8, 6, 26, 18)


def _write(path: Path, orientation: int | None, size: tuple[int, int] = STORED) -> None:
    image = Image.new("RGB", size, (20, 120, 220))
    image.paste((230, 20, 20), MARK)
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(path, exif=exif)


def _dataset(db: Database, tmp_path: Path, orientations: dict[str, int | None]) -> list[FileItem]:
    folder = tmp_path / "oriented"
    folder.mkdir()
    for name, orientation in orientations.items():
        _write(folder / name, orientation, (40, 40) if name.startswith("square") else STORED)
    dataset = import_paths(db, "Oriented", [folder / name for name in orientations])
    version = list_versions(db, dataset.id)[0]
    with db.session() as session:
        row = session.get(VersionRow, version.id)
        assert row is not None
        return [FileItem.model_validate(item) for item in row.manifest]


def test_import_records_upright_size_stored_size_and_orientation(
    db: Database, tmp_path: Path
) -> None:
    """The public width/height are upright; stored size and the EXIF value are kept beside them."""
    names: dict[str, int | None] = {f"o{value}.png": value for value in range(1, 9)}
    names["plain.png"] = None
    files = {item.filename: item.metadata for item in _dataset(db, tmp_path, names)}
    for name, orientation in names.items():
        swapped = orientation is not None and orientation >= 5
        assert files[name]["orientation"] == (orientation or 1)
        assert (files[name]["stored_width"], files[name]["stored_height"]) == STORED
        assert (files[name]["width"], files[name]["height"]) == (
            STORED[::-1] if swapped else STORED
        )


def test_older_imports_backfill_geometry_from_the_header(db: Database, tmp_path: Path) -> None:
    """A manifest written before orientation was recorded resolves it from the stored object."""
    (item,) = _dataset(db, tmp_path, {"o6.png": 6})
    legacy = item.model_copy(
        update={
            "metadata": {
                key: value
                for key, value in item.metadata.items()
                if key not in {"orientation", "stored_width", "stored_height"}
            }
            | {"width": 60, "height": 40}
        }
    )
    assert file_geometry(legacy) == ImageGeometry(orientation=6, stored_width=60, stored_height=40)
    assert file_geometry(item) == file_geometry(legacy)


def _project(
    db: Database, tmp_path: Path, names: dict[str, int | None]
) -> tuple[str, ServiceRunner]:
    _dataset(db, tmp_path, names)
    with db.session() as session:
        version_id = session.query(VersionRow).one().id
    runner = ServiceRunner(db)
    runner("create_label_set", {"label_set_id": "o", "labels": [{"id": "mark", "name": "Mark"}]})
    runner("publish_label_set", {"label_set_id": "o", "version": 1})
    project = runner(
        "create_project",
        {
            "name": "Oriented",
            "dataset_id": _dataset_id(db),
            "version_id": version_id,
            "label_set_id": "o",
        },
    ).root["id"]
    assert isinstance(project, str)
    runner("split_packages", {"project_id": project, "package_size": 20})
    runner(
        "register_model",
        {"model": {"id": "det", "name": "Detector", "version": "v1", "provider": "import"}},
    )
    return project, runner


def _dataset_id(db: Database) -> str:
    with db.session() as session:
        return session.query(VersionRow).one().dataset_id


def _model_box(db: Database, project: str, filename: str) -> AnnotationBox:
    for task in list_tasks(db, project):
        with db.session() as session:
            row = session.get(ProductionTaskRow, task.id)
            assert row is not None
            if row.latest_revision_id is None:
                continue
            revision = session.get(ProductionRevisionRow, row.latest_revision_id)
            assert revision is not None
            assert revision.coordinate_frame == "display"
            value = AnnotationRevision.model_validate(revision.payload)
            if _filename(db, value.annotation.sample_id) == filename:
                [box] = list(value.annotation.boxes or ())
                return box
    raise AssertionError(filename)


def _filename(db: Database, sample_id: str) -> str:
    with db.session() as session:
        row = session.query(VersionRow).one()
        return next(item["filename"] for item in row.manifest if item["id"] == sample_id)


def _import(runner: ServiceRunner, project: str, files: list[dict[str, object]]) -> None:
    runner(
        "import_predictions",
        {
            "project_id": project,
            "model_id": "det",
            "format": "coco",
            "category_mapping": {"1": "mark"},
            "files": files,
        },
    )


def _coco(name: str, width: int, height: int, box: tuple[float, ...]) -> dict[str, object]:
    document = {
        "images": [{"id": 1, "file_name": name, "width": width, "height": height}],
        "annotations": [{"image_id": 1, "category_id": 1, "bbox": list(box)}],
        "categories": [{"id": 1, "name": "mark"}],
    }
    return {"filename": f"{name}.json", "content": json.dumps(document)}


def _upright(x1: float, y1: float, x2: float, y2: float, orientation: int) -> tuple[float, ...]:
    geometry = ImageGeometry(orientation=orientation, stored_width=60, stored_height=40)
    corners = [to_display(geometry, x, y) for x, y in ((x1, y1), (x2, y2))]
    xs, ys = sorted(point[0] for point in corners), sorted(point[1] for point in corners)
    return (xs[0], ys[0], xs[1], ys[1])


def test_coco_frame_follows_declared_size_and_explicit_override(
    db: Database, tmp_path: Path
) -> None:
    """Upright size means upright boxes; stored size means stored boxes, converted on import."""
    names: dict[str, int | None] = {"up.png": 6, "raw.png": 6}
    project, runner = _project(db, tmp_path, names)
    upright = _upright(*MARK, 6)
    _import(
        runner,
        project,
        [
            _coco(
                "up.png",
                40,
                60,
                (upright[0], upright[1], upright[2] - upright[0], upright[3] - upright[1]),
            ),
            _coco("raw.png", 60, 40, (8, 6, 18, 12)),
        ],
    )
    for name in ("up.png", "raw.png"):
        box = _model_box(db, project, name)
        assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx(upright)


def test_square_coco_defaults_to_upright_and_yolo_is_upright(db: Database, tmp_path: Path) -> None:
    """A square image cannot reveal its frame; YOLO is normalized to the upright image."""
    names: dict[str, int | None] = {"square.png": 6, "square-raw.png": 6, "tall.png": 6}
    project, runner = _project(db, tmp_path, names)
    explicit = {**_coco("square-raw.png", 40, 40, (2, 4, 10, 20)), "coordinate_frame": "stored"}
    _import(runner, project, [_coco("square.png", 40, 40, (2, 4, 10, 20)), explicit])
    box = _model_box(db, project, "square.png")
    assert (box.x1, box.y1, box.x2, box.y2) == (2, 4, 12, 24)
    box = _model_box(db, project, "square-raw.png")
    assert (box.x1, box.y1, box.x2, box.y2) == (16, 2, 36, 12)
    upright = _upright(*MARK, 6)
    centre = ((upright[0] + upright[2]) / 80, (upright[1] + upright[3]) / 120)
    size = ((upright[2] - upright[0]) / 40, (upright[3] - upright[1]) / 60)
    runner(
        "import_predictions",
        {
            "project_id": project,
            "model_id": "det",
            "format": "yolo",
            "category_mapping": {"0": "mark"},
            "files": [
                {
                    "filename": "tall.txt",
                    "content": f"0 {centre[0]} {centre[1]} {size[0]} {size[1]}\n",
                }
            ],
        },
    )
    box = _model_box(db, project, "tall.png")
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx(upright)


def _legacy_revision(db: Database, project: str, box: tuple[float, float, float, float]) -> str:
    """Write a v0.18-style head: stored-frame coordinates and no coordinate_frame marker."""
    (task,) = list_tasks(db, project)
    revision = AnnotationRevision(
        id="legacy-revision",
        task_id=task.id,
        previous_revision_id=None,
        actor="annotator",
        created_at=utcnow(),
        annotation=AnnotationRecord(
            sample_id=task.sample_id,
            annotator_id="annotator",
            image_width=60,
            image_height=40,
            boxes=(AnnotationBox(category="mark", x1=box[0], y1=box[1], x2=box[2], y2=box[3]),),
        ),
    )
    with db.session() as session:
        session.add(
            ProductionRevisionRow(
                id=revision.id,
                task_id=task.id,
                project_id=project,
                source="human",
                actor="annotator",
                payload=revision.model_dump(mode="json"),
            )
        )
        row = session.get(ProductionTaskRow, task.id)
        assert row is not None
        row.latest_revision_id = revision.id
        session.commit()
    return task.id


@pytest.mark.parametrize("orientation", range(1, 9))
def test_legacy_stored_frame_heads_are_read_upright_on_the_same_object(
    db: Database, tmp_path: Path, orientation: int
) -> None:
    """A v0.18 box still frames the red mark on the upright canvas; the row is never rewritten."""
    project, _ = _project(db, tmp_path, {"legacy.png": orientation})
    task_id = _legacy_revision(db, project, (8, 6, 26, 18))
    with db.session() as session:
        before = session.get(ProductionRevisionRow, "legacy-revision")
        assert before is not None
        stored_payload = json.dumps(before.payload, sort_keys=True)
    with TestClient(create_app(db)) as client:
        reads: list[WorkbenchTask] = []
        for _ in range(2):
            db.migrate()
            response = client.get(f"/api/production/tasks/{task_id}/workbench")
            assert response.status_code == 200, response.text
            reads.append(WorkbenchTask.model_validate(response.json()))
        image = client.get(reads[0].sample.content_url)
    assert reads[0] == reads[1]
    (revision,) = reads[0].revisions
    [box] = list(revision.annotation.boxes or ())
    pixels = np.asarray(Image.open(io.BytesIO(image.content)).convert("RGB"))
    red = (pixels[..., 0] > 180) & (pixels[..., 2] < 90)
    x1, y1, x2, y2 = (round(value) for value in (box.x1, box.y1, box.x2, box.y2))
    assert red[y1:y2, x1:x2].all()
    assert int(red.sum()) == (x2 - x1) * (y2 - y1)
    assert (revision.annotation.image_width, revision.annotation.image_height) == (
        reads[0].sample.image_width,
        reads[0].sample.image_height,
    )
    if orientation == 1:
        assert revision.coordinate_conversion is None
    else:
        assert revision.coordinate_conversion is not None
        assert revision.coordinate_conversion.orientation == orientation
    with db.session() as session:
        after = session.get(ProductionRevisionRow, "legacy-revision")
        assert after is not None
        assert after.coordinate_frame is None
        assert json.dumps(after.payload, sort_keys=True) == stored_payload


def test_served_canvas_and_thumbnail_match_what_a_browser_shows(
    db: Database, tmp_path: Path
) -> None:
    """Every EXIF value is served as the exif_transpose of the original, without the tag."""
    names: dict[str, int | None] = {f"o{value}.png": value for value in range(1, 9)}
    project, _ = _project(db, tmp_path, names)
    with TestClient(create_app(db)) as client:
        for task in list_tasks(db, project):
            view = WorkbenchTask.model_validate(
                client.get(f"/api/production/tasks/{task.id}/workbench").json()
            )
            orientation = int(view.sample.name[1])
            source = Image.new("RGB", STORED, (20, 120, 220))
            source.paste((230, 20, 20), MARK)
            source.getexif()[274] = orientation
            expected = ImageOps.exif_transpose(source)
            assert (view.sample.image_width, view.sample.image_height) == expected.size
            served = Image.open(io.BytesIO(client.get(view.sample.content_url).content))
            assert served.getexif().get(274) in (None, 1)
            assert np.array_equal(np.asarray(served.convert("RGB")), np.asarray(expected))
            thumbnail = Image.open(io.BytesIO(client.get(view.sample.thumbnail_url or "").content))
            assert thumbnail.size == expected.size


def test_rotated_jpeg_is_served_as_upright_jpeg_and_revalidated(
    db: Database, tmp_path: Path
) -> None:
    """A phone JPEG stays a JPEG once upright; a repeat view under the same grant gets a 304."""
    project, _ = _project(db, tmp_path, {"phone.jpg": 6})
    with TestClient(create_app(db)) as client:
        (task,) = list_tasks(db, project)
        view = WorkbenchTask.model_validate(
            client.get(f"/api/production/tasks/{task.id}/workbench").json()
        )
        for url in (view.sample.content_url, view.sample.thumbnail_url or ""):
            first = client.get(url)
            assert first.headers["content-type"] == "image/jpeg"
            served = Image.open(io.BytesIO(first.content))
            assert served.getexif().get(274) in (None, 1)
            assert served.size == STORED[::-1]
            pixels = np.asarray(served.convert("RGB")).astype(int)
            assert np.abs(pixels[10, 30] - (230, 20, 20)).max() < 24, "red mark moved upright"
            again = client.get(url, headers={"If-None-Match": first.headers["etag"]})
            assert (again.status_code, again.content) == (304, b"")
