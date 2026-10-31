# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""YOLO uses the size recorded at import; multi-image COCO results import by `image_id`."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PIL import Image

from datakeel.api.app import create_app
from datakeel.core.errors import DatakeelError
from datakeel.core.models import FileItem
from datakeel.storage.database import VersionRow
from datakeel.storage.dataset_service import import_paths, list_versions
from tests.asgi_client import TestClient
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.models import JsonDocument
    from datakeel.storage.database import Database

SIZES = {f"cam-{index}.png": (40 + index * 8, 30 + index * 2) for index in range(5)}


def _project(db: Database, tmp_path: Path) -> tuple[str, dict[str, str], ServiceRunner]:
    """Five readable images and one unreadable file imported flat, plus an import model."""
    folder = tmp_path / "flat"
    folder.mkdir()
    for name, size in SIZES.items():
        Image.new("RGB", size, (90, 120, 60)).save(folder / name)
    (folder / "broken.png").write_bytes(b"not an image")
    paths = [folder / name for name in [*SIZES, "broken.png"]]
    dataset = import_paths(db, "Sized images", paths)
    version = list_versions(db, dataset.id)[0]
    with db.session() as session:
        row = session.get(VersionRow, version.id)
        assert row is not None
        files = [FileItem.model_validate(item) for item in row.manifest]
    runner = ServiceRunner(db)
    runner("create_label_set", {"label_set_id": "sized", "labels": [{"id": "cat", "name": "Cat"}]})
    runner("publish_label_set", {"label_set_id": "sized", "version": 1})
    project = runner(
        "create_project",
        {
            "name": "Sized",
            "dataset_id": dataset.id,
            "version_id": version.id,
            "label_set_id": "sized",
        },
    ).root["id"]
    assert isinstance(project, str)
    runner("split_packages", {"project_id": project, "package_size": 10})
    runner(
        "register_model",
        {"model": {"id": "detector", "name": "Detector", "version": "v1", "provider": "import"}},
    )
    return project, {item.filename: item.id for item in files}, runner


def _import(
    runner: ServiceRunner, project: str, fmt: str, files: list[dict[str, object]]
) -> JsonDocument:
    return runner(
        "import_predictions",
        {
            "project_id": project,
            "model_id": "detector",
            "format": fmt,
            "category_mapping": {"0": "cat", "7": "cat"},
            "files": files,
        },
    )


def test_image_import_records_width_and_height_or_unknown(db: Database, tmp_path: Path) -> None:
    """Readable images record their header size; an unreadable one records both as unknown."""
    _, ids, _ = _project(db, tmp_path)
    with db.session() as session:
        rows = session.query(VersionRow).all()
        files = {item["filename"]: item["metadata"] for row in rows for item in row.manifest}
    for name, (width, height) in SIZES.items():
        assert (files[name]["width"], files[name]["height"]) == (width, height)
    assert "width" in files["broken.png"]
    assert (files["broken.png"]["width"], files["broken.png"]["height"]) == (None, None)
    assert set(ids) == {*SIZES, "broken.png"}


def test_yolo_without_width_and_height_uses_the_recorded_image_size(
    db: Database, tmp_path: Path
) -> None:
    """Normalized boxes scale by the size read at import, not by a guessed default."""
    project, ids, runner = _project(db, tmp_path)
    result = _import(
        runner,
        project,
        "yolo",
        [
            {"filename": "cam-1.txt", "content": "0 0.5 0.5 0.5 0.5 0.9"},
            {"filename": "renamed.txt", "sample_id": ids["cam-4.png"], "content": "0 0.5 0.5 1 1"},
        ],
    )
    assert result.root["failures"] == []
    assert len(result.root["revision_ids"]) == 2  # type: ignore[arg-type]


def test_yolo_for_an_image_without_a_recorded_size_is_refused_naming_it(
    db: Database, tmp_path: Path
) -> None:
    """The HTTP execution answers 422 and says which image has no size."""
    project, ids, _ = _project(db, tmp_path)
    client = TestClient(create_app(db))
    body = {
        "request_id": "yolo-unknown",
        "project_id": project,
        "model_id": "detector",
        "format": "yolo",
        "files": [
            {"filename": "b.txt", "sample_id": ids["broken.png"], "content": "0 0.5 0.5 1 1"}
        ],
    }
    plan = client.post("/api/actions/import_predictions/prepare", json=body).json()
    assert plan["reversible"] is True  # Model revisions are reversible: no approval step.
    response = client.post(
        f"/api/actions/{plan['id']}/execute",
        json={"plan_digest": plan["plan_digest"], "actor": "local"},
    )
    assert response.status_code == 422
    assert "broken.png" in response.text
    assert "b.txt" in response.text


def test_coco_results_array_imports_five_images_and_lists_what_does_not_match(
    db: Database, tmp_path: Path
) -> None:
    """Five matched images give five revisions; an unknown id and an unknown size are listed."""
    project, ids, runner = _project(db, tmp_path)
    results = [
        {"image_id": ids[name], "category_id": 7, "bbox": [1, 1, 8, 6], "score": 0.8}
        for name in SIZES
    ]
    results += [
        {"image_id": ids["cam-0.png"], "category_id": 7, "bbox": [2, 2, 4, 4], "score": 0.6},
        {"image_id": "ghost-17", "category_id": 7, "bbox": [0, 0, 5, 5]},
        {"image_id": "ghost-17", "category_id": 7, "bbox": [1, 1, 5, 5]},
        {"image_id": ids["broken.png"], "category_id": 7, "bbox": [0, 0, 5, 5]},
    ]
    content = json.dumps(results)
    result = _import(runner, project, "coco", [{"filename": "results.json", "content": content}])
    assert len(result.root["revision_ids"]) == 5  # type: ignore[arg-type]
    failures = {item["code"]: item for item in result.root["failures"]}  # type: ignore[union-attr,index]
    assert set(failures) == {"unknown_image", "unknown_size"}
    assert "ghost-17" in str(failures["unknown_image"]["message"])
    assert "2 results" in str(failures["unknown_image"]["message"])
    assert failures["unknown_size"]["filename"] == "broken.png"


def _outcome(runner: ServiceRunner, project: str, fmt: str, files: list[dict[str, object]]) -> str:
    """Turn any refusal into text so a guard fails on its assertion, never on a crash."""
    try:
        result = _import(runner, project, fmt, files)
    except (DatakeelError, TypeError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return json.dumps(result.root["failures"])


def test_import_size_mutation_guard(db: Database, tmp_path: Path) -> None:
    """One measured anchor: sizes are stored at import, unknown sizes refuse, unknown ids list."""
    project, ids, runner = _project(db, tmp_path)
    # Reads backfill a missing size from the image header, so check the stored manifest itself.
    with db.session() as session:
        rows = session.query(VersionRow).all()
        stored = {item["filename"]: item["metadata"] for row in rows for item in row.manifest}
    assert stored["cam-2.png"].get("width") == SIZES["cam-2.png"][0]
    plain = [{"filename": "cam-2.txt", "content": "0 0.5 0.5 1 1"}]
    assert _outcome(runner, project, "yolo", plain) == "[]"
    unknown = [{"filename": "u.txt", "sample_id": ids["broken.png"], "content": "0 0.5 0.5 1 1"}]
    refused = _outcome(runner, project, "yolo", unknown)
    assert refused.startswith("ValidationError")
    assert "broken.png" in refused
    ghosts = json.dumps([{"image_id": "ghost-3", "category_id": 7, "bbox": [0, 0, 5, 5]}])
    listed = _outcome(runner, project, "coco", [{"filename": "g.json", "content": ghosts}])
    assert json.loads(listed)[0]["filename"] == "ghost-3"
