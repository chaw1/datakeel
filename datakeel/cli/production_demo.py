# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate a small personal box-labeling project with imported offline model predictions."""

import json

from PIL import Image

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.core.models import BoundaryModel, JsonDocument, new_id
from datakeel.core.settings import get_settings
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_queries import list_tasks


class ProductionDemoResult(BoundaryModel):
    """Identify the generated project and input facts for the next workbench phase."""

    project_id: str
    dataset_id: str
    version_id: str
    label_set_id: str
    model_id: str
    task_ids: tuple[str, ...]


def _run(db: Database, name: str, values: JsonDocument) -> JsonDocument:
    plan = service.prepare_action(db, name, values)
    if plan.requires_approval:
        service.approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest)
        )
    run = service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.receipt is None:
        message = "Production demo action returned no receipt"
        raise RuntimeError(message)
    return JsonDocument.model_validate(run.receipt.quality["details"])


def seed_production_demo(db: Database) -> ProductionDemoResult:
    """Create generated images and use signed public actions to seed a resumable project."""
    root = get_settings().home / "production-demo" / new_id()
    root.mkdir(parents=True)
    paths = [root / f"sample-{index}.png" for index in range(3)]
    for index, path in enumerate(paths):
        image = Image.new("RGB", (100, 100), (50 + index * 30, 120, 180))
        image.save(path)
    dataset = import_paths(db, "Production demo", paths)
    version_id = list_versions(db, dataset.id)[-1].id
    label_set_id, model_id = _demo_rules(db)
    project = _run(
        db,
        "create_project",
        JsonDocument(
            {
                "request_id": new_id(),
                "name": "Personal box labeling",
                "dataset_id": dataset.id,
                "version_id": version_id,
                "label_set_id": label_set_id,
            }
        ),
    )
    project_id = str(project.root["id"])
    _run(
        db,
        "split_packages",
        JsonDocument(
            {
                "request_id": new_id(),
                "project_id": project_id,
                "package_size": 3,
            }
        ),
    )
    tasks = list_tasks(db, project_id)
    _import_demo_predictions(db, project_id, model_id, tuple(task.sample_id for task in tasks))
    return ProductionDemoResult(
        project_id=project_id,
        dataset_id=dataset.id,
        version_id=version_id,
        label_set_id=label_set_id,
        model_id=model_id,
        task_ids=tuple(task.id for task in tasks),
    )


def _demo_rules(db: Database) -> tuple[str, str]:
    labels = _run(
        db,
        "create_label_set",
        JsonDocument(
            {
                "request_id": new_id(),
                "name": "Demo boxes",
                "labels": [{"id": "object", "name": "Object"}],
            }
        ),
    )
    label_set_id = str(labels.root["id"])
    _run(
        db,
        "publish_label_set",
        JsonDocument(
            {
                "request_id": new_id(),
                "label_set_id": label_set_id,
                "version": 1,
            }
        ),
    )
    model_id = "demo-" + new_id()
    _run(
        db,
        "register_model",
        JsonDocument(
            {
                "request_id": new_id(),
                "model": {
                    "id": model_id,
                    "name": "Generated predictions",
                    "version": "1",
                    "provider": "import",
                },
            }
        ),
    )
    return label_set_id, model_id


def _import_demo_predictions(
    db: Database, project_id: str, model_id: str, sample_ids: tuple[str, ...]
) -> None:
    document = {
        "images": [
            {"id": index, "file_name": sample_id, "width": 100, "height": 100}
            for index, sample_id in enumerate(sample_ids)
        ],
        "categories": [{"id": 1, "name": "object"}],
        "annotations": [
            {
                "id": index,
                "image_id": index,
                "category_id": 1,
                "bbox": [10, 10, 40, 30],
                "score": 0.8,
            }
            for index in range(len(sample_ids))
        ],
    }
    _run(
        db,
        "import_predictions",
        JsonDocument(
            {
                "request_id": new_id(),
                "project_id": project_id,
                "model_id": model_id,
                "format": "coco",
                "files": [{"filename": "generated.json", "content": json.dumps(document)}],
            }
        ),
    )
