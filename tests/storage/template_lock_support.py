# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Two projects sharing one template and label set, for template-lock and upgrade tests."""

from pathlib import Path

from PIL import Image

from datakeel.actions.models import ActionContext, ActionPlan
from datakeel.actions.service import prepare_action
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.production_models import ProductionTask, Project
from datakeel.core.production_upgrade_models import TemplateUpgradePlan
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_catalog import require_template
from datakeel.storage.production_queries import list_tasks
from tests.production_flow_support import action_payload
from tests.workbench_helpers import run_action

LABELS = "lock-labels"
TEMPLATE = "lock-template"
REQUIRED_COLOUR = {
    "key": "colour",
    "name_zh": "颜色",
    "name_en": "Colour",
    "type": "enum",
    "options": [
        {"value": "red", "name_zh": "红", "name_en": "Red"},
        {"value": "blue", "name_zh": "蓝", "name_en": "Blue"},
    ],
    "required": True,
}


def seed_two_projects(
    db: Database, directory: Path, count: int = 3
) -> tuple[tuple[Project, tuple[ProductionTask, ...]], ...]:
    """Create two box projects over the same images, template and published labels v1."""
    directory.mkdir(parents=True)
    paths: list[Path] = []
    for index in range(count):
        path = directory / f"image-{index}.png"
        with Image.new("RGB", (100, 80), (20 + index, 90, 150)) as image:
            image.save(path)
        paths.append(path)
    dataset = import_paths(db, "Template lock", paths)
    version = list_versions(db, dataset.id)[0]
    run_action(
        db,
        "create_label_set",
        {
            "label_set_id": LABELS,
            "labels": [{"id": "cat", "name": "Cat"}, {"id": "dog", "name": "Dog"}],
        },
    )
    run_action(db, "publish_label_set", {"label_set_id": LABELS, "version": 1})
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "template": {"id": TEMPLATE, "name": "Lock", "annotation_type": "box"},
        },
    )
    projects: list[tuple[Project, tuple[ProductionTask, ...]]] = []
    for name in ("First", "Second"):
        project = Project.model_validate(
            run_action(
                db,
                "create_project",
                {
                    "name": name,
                    "dataset_id": dataset.id,
                    "version_id": version.id,
                    "label_set_id": LABELS,
                    "template_id": TEMPLATE,
                },
            ).root
        )
        run_action(db, "split_packages", {"project_id": project.id, "package_size": 100})
        projects.append((project, list_tasks(db, project.id)))
    return tuple(projects)


def change_template(db: Database) -> None:
    """Add a required box attribute (template v2) and delete the dog label (labels v2)."""
    with db.session() as session:
        current = require_template(session, TEMPLATE)
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "update",
            "template": {
                **current.model_dump(mode="json"),
                "attributes": [REQUIRED_COLOUR],
            },
        },
    )
    run_action(
        db,
        "create_label_set",
        {
            "label_set_id": LABELS,
            "labels": [{"id": "cat", "name": "Cat"}, {"id": "bird", "name": "Bird"}],
            "migration": [{"operation": "delete", "source_ids": ["dog"], "strategy": "drop"}],
        },
    )
    run_action(db, "publish_label_set", {"label_set_id": LABELS, "version": 2})


def box(category: str, x1: float = 1, **attributes: object) -> dict[str, object]:
    """Return one valid 100x80 box with optional attributes."""
    return {
        "category": category,
        "x1": x1,
        "y1": 1,
        "x2": x1 + 10,
        "y2": 20,
        "attributes": attributes,
    }


def save(db: Database, task: ProductionTask, boxes: list[dict[str, object]]) -> str:
    """Append one human revision on a task's current head and return its id."""
    details = run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": None,
            "annotation": {
                "sample_id": task.sample_id,
                "annotator_id": "local",
                "image_width": 100,
                "image_height": 80,
                "boxes": boxes,
            },
        },
    )
    return str(details.root["id"])


def prepare_upgrade(db: Database, project_id: str, **values: object) -> ActionPlan:
    """Prepare the controlled upgrade without signing it."""
    return prepare_action(
        db,
        "upgrade_project_template",
        action_payload(
            "upgrade_project_template", {"project_id": project_id, "request_id": new_id(), **values}
        ),
        ActionContext(actor="local"),
    )


def plan_details(plan: ActionPlan) -> TemplateUpgradePlan:
    """Read the computed upgrade shown on the plan's project object."""
    project = next(item for item in plan.manifest.objects if item.asset_ref.asset_type == "project")
    return TemplateUpgradePlan.model_validate(
        JsonDocument.model_validate(project.properties).root["template_upgrade"]
    )
