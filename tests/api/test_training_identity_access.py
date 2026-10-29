# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training split, export and text-governance writes follow registered role scopes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.annotation_models import AnnotationBatch, AnnotationBox, AnnotationRecord
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.models import JsonDocument, new_id
from datakeel.storage.annotation_store import import_annotations
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.identity_store import role_templates
from tests.asgi_client import TestClient
from tests.storage.llm_data_helpers import seed_training

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _run(db: Database, action: str, values: dict[str, object], actor: str = "local") -> None:
    plan = prepare_action(
        db,
        action,
        JsonDocument.model_validate({"request_id": new_id(), **values}),
        ActionContext(actor=actor),
    )
    if plan.requires_approval:
        approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor)
        )
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor))
    assert run.status == "SUCCEEDED"


def _images(db: Database, directory: Path) -> tuple[str, str]:
    paths = []
    for index in range(6):
        path = directory / f"identity-{index}.png"
        Image.new("RGB", (40, 30), (index * 30, 20, 60)).save(path)
        paths.append(path)
    dataset = import_paths(db, "Training identity", paths)
    version = list_versions(db, dataset.id)[0]
    batch = AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(
                sample_id=file.id,
                annotator_id="r",
                labels=("cat",),
                boxes=(AnnotationBox(category="cat", x1=2, y1=3, x2=20, y2=25),),
                image_width=40,
                image_height=30,
            )
            for file in version.manifest
        )
    )
    import_annotations(
        db,
        dataset.id,
        AnnotationImportRequest(version_id=version.id, idempotency_key="identity", batch=batch),
    )
    return dataset.id, version.id


def test_project_manager_template_exports_training_but_cannot_clean_or_import(
    db: Database, tmp_path: Path
) -> None:
    """Managers export finalized work; observers preview; dataset writes stay administrative."""
    templates = {role.id: set(role.scopes) for role in role_templates()}
    assert "datasets:export" in templates["project_manager"]
    assert "datasets:write" not in templates["project_manager"]
    assert templates["acceptance"] == set()
    dataset, version = _images(db, tmp_path)
    text_dataset, _, run = seed_training(db, tmp_path)
    prefix = f"/api/datasets/{dataset}/versions/{version}/training"
    split = {"name": "identity", "avoid_leakage": False}
    with TestClient(create_app(db)) as client:
        assert client.post(f"{prefix}/splits", json=split).status_code == 201
        _run(db, "manage_users", {"operation": "create", "user_id": "local"})
        for user, role in (("pm", "project_manager"), ("observer", "acceptance")):
            _run(db, "manage_users", {"operation": "create", "user_id": user, "role_ids": [role]})
        observer = {"X-Datakeel-Actor": "observer"}
        manager = {"X-Datakeel-Actor": "pm"}
        preview = client.post(f"{prefix}/preview", json=split, headers=observer)
        assert preview.status_code == 200, preview.text
        assert client.post(f"{prefix}/leakage", json=split, headers=observer).status_code == 200
        assert client.post(f"{prefix}/splits", json=split, headers=observer).status_code == 403
        created = client.post(
            f"{prefix}/splits", json={**split, "name": "manager"}, headers=manager
        )
        assert created.status_code == 201, created.text
        export = {
            "dataset_id": dataset,
            "version_id": version,
            "split_set_id": created.json()["id"],
            "format": "coco",
        }
        for actor, status in (("observer", 403), ("pm", 200)):
            prepared = client.post(
                "/api/actions/export_dataset/prepare",
                json=export,
                headers={"X-Datakeel-Actor": actor},
            )
            assert prepared.status_code == status, prepared.text
        assert prepared.json()["actor"] == "pm"
        for path in (
            f"{prefix}/import-annotations",
            f"/api/datasets/{text_dataset}/text-governance/analyze",
            f"/api/datasets/{text_dataset}/text-governance/evaluations",
            f"/api/training-governance/{run.id}/clean",
        ):
            assert client.post(path, json={}, headers=manager).status_code == 403, path


def test_text_governance_preparation_keeps_the_registered_http_actor(
    db: Database, tmp_path: Path
) -> None:
    """A dataset steward's clean plan is attributed to the steward instead of local."""
    dataset, _, _ = seed_training(db, tmp_path)
    _run(db, "manage_users", {"operation": "create", "user_id": "local"})
    _run(
        db,
        "define_role",
        {"role_id": "steward", "name": "Dataset steward", "scopes": ["datasets:write"]},
    )
    _run(db, "manage_users", {"operation": "create", "user_id": "steward", "role_ids": ["steward"]})
    headers = {"X-Datakeel-Actor": "steward"}
    with TestClient(create_app(db)) as client:
        analysis = client.post(
            f"/api/datasets/{dataset}/text-governance/analyze", json={}, headers=headers
        )
        assert analysis.status_code == 200, analysis.text
        plan = client.post(
            f"/api/training-governance/{analysis.json()['id']}/clean", headers=headers
        )
        assert plan.status_code == 200, plan.text
        assert plan.json()["actor"] == "steward"
        assert plan.json()["action_type"] == "clean_training_data"
