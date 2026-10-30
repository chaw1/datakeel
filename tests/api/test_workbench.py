# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native-grant protected workbench configuration, media and immutable history reads."""

import io
from pathlib import Path

from PIL import Image

from datakeel.api.app import create_app
from datakeel.core.models import AssetRef
from datakeel.core.workbench_models import WorkbenchIndex, WorkbenchProject, WorkbenchTask
from datakeel.storage.database import Database
from datakeel.storage.production_queries import project_progress
from datakeel.storage.production_statistics import annotator_workload, confidence_distribution
from tests.asgi_client import TestClient
from tests.assets.entry_helpers import grant, publish
from tests.workbench_helpers import annotation_for, run_action, seed_workbench


def test_workbench_reads_native_facts_history_and_authorized_content(
    db: Database, tmp_path: Path
) -> None:
    """The shell receives exact P29 facts and source bytes without private paths or keys."""
    project, tasks = seed_workbench(db, tmp_path / "sources")
    first = tasks[0]
    run_action(
        db,
        "save_revision",
        {
            "task_id": first.id,
            "previous_revision_id": None,
            "annotation": annotation_for("box", first.sample_id).model_dump(mode="json"),
        },
    )
    with TestClient(create_app(db)) as client:
        index = WorkbenchIndex.model_validate(client.get("/api/production/workbench").json())
        assert index.zero_users
        assert index.actor == "local"
        assert index.projects == (project,)
        response = client.get(f"/api/production/projects/{project.id}/workbench?limit=1&cursor=")
        assert response.status_code == 200, response.text
        value = WorkbenchProject.model_validate(response.json())
        assert value.progress == project_progress(db, project.id)
        assert value.workload == annotator_workload(db, project.id)
        assert value.confidence == confidence_distribution(db, project.id)
        assert value.template is not None
        assert value.template.id == project.template_id
        assert value.label_set.id == project.label_set_id
        assert len(value.tasks) == 1
        assert value.next_cursor == value.tasks[-1].id
        following = client.get(
            f"/api/production/projects/{project.id}/workbench",
            params={"limit": 1, "cursor": value.next_cursor},
        )
        assert following.json()["tasks"][0]["id"] != value.tasks[0].id
        detail = client.get(f"/api/production/tasks/{first.id}/workbench")
        assert detail.status_code == 200, detail.text
        task = WorkbenchTask.model_validate(detail.json())
        assert task.sample.image_width == 100
        assert task.sample.image_height == 80
        assert task.revisions[0].annotation.boxes is not None
        assert task.revisions[0].annotation.boxes[0].attributes == {"occluded": True}
        assert "object_key" not in detail.text
        assert str(tmp_path) not in detail.text
        content = client.get(task.sample.content_url)
        assert content.status_code == 200
        assert content.headers["content-type"] == "image/png"
        preview = client.get(task.sample.thumbnail_url or "")
        with Image.open(io.BytesIO(preview.content)) as image:
            assert image.width <= 1024
            assert image.height <= 1024
        assert (
            client.get(f"/api/production/projects/{project.id}/workbench?limit=0").status_code
            == 422
        )


def test_workbench_protected_project_and_media_require_current_actor_grant(
    db: Database, tmp_path: Path
) -> None:
    """Discovery hides inaccessible sources and bypassing the UI still rejects their content."""
    project, tasks = seed_workbench(db, tmp_path / "protected")
    run_action(db, "manage_users", {"operation": "create", "user_id": "local"})
    asset = publish(db, AssetRef(asset_id=project.dataset_id, version=project.version_id))
    grant(db, asset, "valid", "query", subject="local")
    grant(db, asset, "valid", "download", subject="local")
    grant(db, asset, "valid", "download", subject="unknown")
    with TestClient(create_app(db)) as client:
        unknown = {"X-Datakeel-Actor": "unknown"}
        listing = client.get("/api/production/workbench", headers=unknown)
        assert listing.status_code == 200
        assert listing.json()["projects"] == []
        assert listing.json()["effective_scopes"]["scopes"] == []
        for url in (
            f"/api/production/projects/{project.id}/workbench",
            f"/api/production/tasks/{tasks[0].id}/workbench",
            f"/api/production/tasks/{tasks[0].id}/content",
            f"/api/production/tasks/{tasks[0].id}/content?thumbnail=true",
        ):
            denied = client.get(url, headers=unknown)
            assert denied.status_code == 403, denied.text
        assert client.get(f"/api/production/tasks/{tasks[0].id}/workbench").status_code == 200
        forbidden = client.post(
            "/api/actions/save_revision/prepare",
            headers=unknown,
            json={
                "request_id": "forbidden",
                "task_id": tasks[0].id,
                "previous_revision_id": None,
                "annotation": annotation_for("box", tasks[0].sample_id).model_dump(mode="json"),
            },
        )
        assert forbidden.status_code == 403


def test_workbench_text_keeps_character_offsets_and_line_endings(
    db: Database, tmp_path: Path
) -> None:
    """Nested text spans target exact decoded source characters, including CRLF sequences."""
    _, tasks = seed_workbench(db, tmp_path / "text", "text_span")
    with TestClient(create_app(db)) as client:
        response = client.get(f"/api/production/tasks/{tasks[0].id}/workbench")
        assert response.status_code == 200, response.text
        sample = WorkbenchTask.model_validate(response.json()).sample
        assert sample.text == "A猫\r\n nested text"
        assert sample.text[1:2] == "猫"
        assert sample.image_width is None


def test_workbench_stale_save_returns_http_conflict_with_authoritative_head(
    db: Database, tmp_path: Path
) -> None:
    """A direct stale write returns 409 and the exact server revision without changing its head."""
    _, tasks = seed_workbench(db, tmp_path / "conflict")
    task = tasks[0]
    body = {
        "task_id": task.id,
        "previous_revision_id": None,
        "annotation": annotation_for("box", task.sample_id).model_dump(mode="json"),
    }
    first = run_action(db, "save_revision", body)
    with TestClient(create_app(db)) as client:
        prepared = client.post(
            "/api/actions/save_revision/prepare", json={"request_id": "stale-write", **body}
        )
        assert prepared.status_code == 200, prepared.text
        plan = prepared.json()
        rejected = client.post(
            f"/api/actions/{plan['id']}/execute",
            json={"plan_digest": plan["plan_digest"], "actor": "local"},
        )
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["latest_revision"]["id"] == first.root["id"]
        detail = client.get(f"/api/production/tasks/{task.id}/workbench").json()
        assert len(detail["revisions"]) == 1
        assert detail["task"]["latest_revision_id"] == first.root["id"]


def test_workbench_large_image_preview_is_downsampled_before_high_resolution_source(
    db: Database, tmp_path: Path
) -> None:
    """Progressive loading receives bounded JPEG pixels while preserving the original source."""
    _, tasks = seed_workbench(db, tmp_path / "large", image_size=(2048, 1536))
    with TestClient(create_app(db)) as client:
        detail = client.get(f"/api/production/tasks/{tasks[0].id}/workbench")
        sample = WorkbenchTask.model_validate(detail.json()).sample
        assert sample.image_width == 2048
        assert sample.image_height == 1536
        preview = client.get(sample.thumbnail_url or "")
        assert preview.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(preview.content)) as image:
            assert image.size == (1024, 768)
        original = client.get(sample.content_url)
        with Image.open(io.BytesIO(original.content)) as image:
            assert image.size == (2048, 1536)


def test_workbench_direct_polygon_save_rejects_outside_image_coordinates(
    db: Database, tmp_path: Path
) -> None:
    """A direct caller receives a validation error for polygon points outside source pixels."""
    _, tasks = seed_workbench(db, tmp_path / "polygon-http", "polygon")
    annotation = annotation_for("polygon", tasks[0].sample_id).model_dump(mode="json")
    annotation["polygons"][0]["points"][1]["x"] = 101
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/actions/save_revision/prepare",
            json={
                "request_id": "invalid-polygon",
                "task_id": tasks[0].id,
                "previous_revision_id": None,
                "annotation": annotation,
            },
        )
        assert response.status_code == 200, response.text
        plan = response.json()
        rejected = client.post(
            f"/api/actions/{plan['id']}/execute",
            json={"plan_digest": plan["plan_digest"], "actor": "local"},
        )
        assert rejected.status_code == 422, rejected.text
        assert "polygon is outside" in rejected.text


def test_workbench_package_filter_precedes_pagination_and_keeps_project_progress(
    db: Database, tmp_path: Path
) -> None:
    """A package outside the first global page remains reachable without changing project totals."""
    project, tasks = seed_workbench(db, tmp_path / "packages", package_size=1)
    with TestClient(create_app(db)) as client:
        response = client.get(
            f"/api/production/projects/{project.id}/workbench",
            params={"package_id": tasks[-1].package_id, "limit": 1, "cursor": ""},
        )
        assert response.status_code == 200, response.text
        result = WorkbenchProject.model_validate(response.json())
        assert result.tasks == (tasks[-1],)
        assert result.next_cursor is None
        assert result.progress == project_progress(db, project.id)
        invalid = client.get(f"/api/production/projects/{project.id}/workbench?package_id=missing")
        assert invalid.status_code == 404


def test_workbench_exif_media_and_thumbnails_use_the_same_upright_pixel_frame(
    db: Database, tmp_path: Path
) -> None:
    """Canvas, thumbnail and reported size all use the EXIF-applied (upright) frame."""
    _, tasks = seed_workbench(db, tmp_path / "oriented", image_size=(100, 80), image_orientation=6)
    with TestClient(create_app(db)) as client:
        response = client.get(f"/api/production/tasks/{tasks[0].id}/workbench")
        assert response.status_code == 200, response.text
        sample = WorkbenchTask.model_validate(response.json()).sample
        assert (sample.image_width, sample.image_height) == (80, 100)
        for url in (sample.content_url, sample.thumbnail_url or ""):
            content = client.get(url)
            assert content.status_code == 200, content.text
            with Image.open(io.BytesIO(content.content)) as image:
                assert image.size == (80, 100)
                assert image.getexif().get(274) in (None, 1)


def test_workbench_mixed_template_accepts_its_configured_components(
    db: Database, tmp_path: Path
) -> None:
    """Configured box and classification components can autosave in one ordinary revision."""
    _, tasks = seed_workbench(db, tmp_path / "mixed-http")
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "update",
            "template": {
                "id": "wb-template",
                "name": "Mixed",
                "revision": 1,
                "component_config": {"components": ["box", "classification"]},
            },
        },
    )
    annotation = annotation_for("box", tasks[0].sample_id).model_copy(update={"labels": ("Cat",)})
    with TestClient(create_app(db)) as client:
        prepared = client.post(
            "/api/actions/save_revision/prepare",
            json={
                "request_id": "mixed",
                "task_id": tasks[0].id,
                "previous_revision_id": None,
                "annotation": annotation.model_dump(mode="json"),
            },
        )
        assert prepared.status_code == 200, prepared.text
        plan = prepared.json()
        saved = client.post(
            f"/api/actions/{plan['id']}/execute",
            json={"plan_digest": plan["plan_digest"], "actor": "local"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "SUCCEEDED"
        response = client.get(f"/api/production/tasks/{tasks[0].id}/workbench")
        result = WorkbenchTask.model_validate(response.json())
        assert result.revisions[0].annotation.labels == ("cat",)
        assert result.revisions[0].annotation.boxes is not None
