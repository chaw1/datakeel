# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete generated production scenarios shared by independent HTTP and CLI transports."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.production_models import (
    AnnotationRevision,
    ProductionTask,
    Project,
    WorkflowTier,
)
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions, require_dataset
from datakeel.storage.datasheet_store import get_document
from datakeel.storage.production_queries import get_task, list_assignments, list_reviews, list_tasks
from datakeel.storage.version_diff import version_summary


class FlowRunner(Protocol):
    """Execute one production action through a concrete public transport and human decisions."""

    def __call__(
        self, action: str, values: Mapping[str, object], actor: str = "local"
    ) -> JsonDocument:
        """Return the succeeded action receipt's typed business details."""
        ...


@dataclass(frozen=True)
class ProductionFlow:
    """Retain immutable project and task boundaries for end-to-end assertions."""

    project: Project
    tasks: tuple[ProductionTask, ...]
    output_version: str | None = None


def action_payload(action: str, values: Mapping[str, object]) -> JsonDocument:
    """Add client replay identities only to schemas that declare them."""
    identity = (
        {"request_id": new_id()} if "request_id" in PARAMETER_TYPES[action].model_fields else {}
    )
    return JsonDocument.model_validate({**identity, **values})


def create_flow(
    db: Database,
    directory: Path,
    runner: FlowRunner,
    tier: WorkflowTier = "personal",
) -> ProductionFlow:
    """Create generated images, approved catalog objects and partitioned tasks."""
    directory.mkdir()
    paths = [directory / f"generated-{index}.png" for index in range(2)]
    for index, path in enumerate(paths):
        Image.new("RGB", (64, 48), (100 + index, 80, 40)).save(path)
    dataset = import_paths(db, "Generated production flow", paths, {"license": "CC0-1.0"})
    source = list_versions(db, dataset.id)[0]
    runner(
        "create_label_set",
        {"label_set_id": "flow-labels", "labels": [{"id": "cat", "name": "Cat"}]},
    )
    runner("publish_label_set", {"label_set_id": "flow-labels", "version": 1})
    runner(
        "create_label_set",
        {"target": "template", "template": {"id": "flow-template", "name": "Boxes"}},
    )
    runner(
        "register_model",
        {
            "model": {
                "id": "flow-model",
                "name": "External generated model",
                "version": "v1",
                "provider": "import",
            }
        },
    )
    project = Project.model_validate(
        runner(
            "create_project",
            {
                "name": "Generated flow",
                "dataset_id": dataset.id,
                "version_id": source.id,
                "label_set_id": "flow-labels",
                "template_id": "flow-template",
                "workflow_tier": tier,
            },
        ).root
    )
    runner("split_packages", {"project_id": project.id, "package_size": 2})
    return ProductionFlow(project, list_tasks(db, project.id))


def personal_flow(db: Database, directory: Path, runner: FlowRunner) -> ProductionFlow:
    """Import both formats, correct one image and finalize approved personal tasks."""
    flow = create_flow(db, directory, runner)
    first, second = flow.tasks
    document = JsonDocument(
        {
            "images": [
                {"id": first.sample_id, "file_name": first.sample_id, "width": 64, "height": 48}
            ],
            "categories": [{"id": 7, "name": "external cat"}],
            "annotations": [
                {
                    "image_id": first.sample_id,
                    "category_id": 7,
                    "bbox": [1, 2, 10, 12],
                    "score": 0.8,
                }
            ],
        }
    )
    coco = runner(
        "import_predictions",
        {
            "project_id": flow.project.id,
            "model_id": "flow-model",
            "format": "coco",
            "category_mapping": {"7": "cat"},
            "files": [{"filename": "coco.json", "content": document.model_dump_json()}],
        },
    )
    assert coco.root["failures"] == []
    yolo = runner(
        "import_predictions",
        {
            "project_id": flow.project.id,
            "model_id": "flow-model",
            "format": "yolo",
            "files": [
                {
                    "filename": "prediction.txt",
                    "sample_id": second.sample_id,
                    "image_width": 64,
                    "image_height": 48,
                    "content": "0 0.5 0.5 0.5 0.5 0.9",
                }
            ],
        },
    )
    assert yolo.root["failures"] == []
    save_task(db, runner, first.id)
    for task in flow.tasks:
        runner("submit_task", {"task_id": task.id})
        assert get_task(db, task.id).state == "approved"
        assert list_assignments(db, task.id) == ()
        assert list_reviews(db, task.id) == ()
    return finalize_flow(db, runner, flow)


def save_task(
    db: Database, runner: FlowRunner, task_id: str, actor: str = "local"
) -> AnnotationRevision:
    """Save one human correction through the public action using the actual current head."""
    task = get_task(db, task_id)
    result = runner(
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": task.latest_revision_id,
            "annotation": {
                "sample_id": task.sample_id,
                "annotator_id": actor,
                "image_width": 64,
                "image_height": 48,
                "boxes": [{"category": "cat", "x1": 2, "y1": 3, "x2": 14, "y2": 18}],
            },
        },
        actor,
    )
    return AnnotationRevision.model_validate(result.root, extra="ignore")


def group_flow(db: Database, directory: Path, runner: FlowRunner) -> ProductionFlow:
    """Complete a group flow with project roles, assignment, claim and explicit rework."""
    runner("manage_users", {"operation": "create", "user_id": "local"})
    flow = create_flow(db, directory, runner, "group")
    _register_members(runner, flow.project.id)
    first = flow.tasks[0]
    runner("assign_tasks", {"task_ids": [first.id], "actor": "ann"})
    claimed = ProductionTask.model_validate(
        runner("claim_task", {"project_id": flow.project.id}, "ann").root, extra="ignore"
    )
    assert claimed.id != first.id
    for task in (first, claimed):
        save_task(db, runner, task.id, "ann")
        runner("submit_task", {"task_id": task.id}, "ann")
    reviewed = ProductionTask.model_validate(
        runner("claim_task", {"project_id": flow.project.id, "stage": "review"}, "qa").root,
        extra="ignore",
    )
    assert reviewed.latest_revision_id is not None
    runner(
        "review_task",
        {
            "task_id": reviewed.id,
            "revision_id": reviewed.latest_revision_id,
            "decision": "rework",
            "issues": ["Correct box boundary"],
        },
        "qa",
    )
    rework = get_task(db, reviewed.id)
    assert (rework.state, rework.round, rework.annotator_id) == ("pending", 1, "ann")
    assert any(
        assignment.active and assignment.actor == "ann"
        for assignment in list_assignments(db, rework.id)
    )
    save_task(db, runner, rework.id, "ann")
    runner("submit_task", {"task_id": rework.id}, "ann")
    for task in flow.tasks:
        current = get_task(db, task.id)
        runner(
            "review_task",
            {
                "task_id": current.id,
                "revision_id": current.latest_revision_id,
                "decision": "approve",
            },
            "qa",
        )
    return finalize_flow(db, runner, flow)


def _register_members(runner: FlowRunner, project_id: str) -> None:
    for actor in ("ann", "qa"):
        runner("manage_users", {"operation": "create", "user_id": actor})
    for actor, role in (("local", "project_manager"), ("ann", "annotator"), ("qa", "reviewer")):
        runner(
            "manage_users",
            {"operation": "bind_role", "user_id": actor, "role_id": role, "project_id": project_id},
        )


def finalize_flow(db: Database, runner: FlowRunner, flow: ProductionFlow) -> ProductionFlow:
    """Verify the produced version feeds existing publication statistics and template datasheets."""
    result = runner("finalize_project", {"project_id": flow.project.id})
    version_id = str(result.root["version_id"])
    assert version_id != flow.project.version_id
    assert result.root["produced_by_project"] == flow.project.id
    with db.session() as session:
        summary = version_summary(
            session, require_dataset(session, flow.project.dataset_id), version_id
        )
    assert (summary.annotation_count, summary.label_count) == (2, 2)
    assert all(get_task(db, task.id).state == "finalized" for task in flow.tasks)
    datasheet = runner(
        "generate_datasheet",
        {
            "dataset_id": flow.project.dataset_id,
            "version_id": version_id,
            "mode": "template",
            "language": "en",
        },
    )
    document = get_document(db, str(datasheet.root["document_id"]))
    assert document.version_id == version_id
    assert document.sections
    assert document.facts
    return ProductionFlow(flow.project, flow.tasks, version_id)
