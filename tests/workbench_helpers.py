# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local workbench sources and real controlled-action setup helpers."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from PIL import Image

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import JsonDocument
from datakeel.core.production_models import ProductionTask, Project
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_queries import list_tasks
from tests.production_flow_support import action_payload

ComponentKind = Literal["box", "polygon", "classification", "text_span"]


def run_action(
    db: Database, action: str, values: Mapping[str, object], actor: str = "local"
) -> JsonDocument:
    """Prepare, explicitly approve when required and execute one real action."""
    plan = prepare_action(db, action, action_payload(action, values), ActionContext(actor=actor))
    if plan.requires_approval:
        approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor)
        )
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor))
    assert run.status == "SUCCEEDED"
    assert run.receipt is not None
    return JsonDocument.model_validate(run.receipt.quality["details"])


def seed_workbench(
    db: Database,
    directory: Path,
    kind: ComponentKind = "box",
    image_size: tuple[int, int] = (100, 80),
    package_size: int = 100,
    image_orientation: int | None = None,
) -> tuple[Project, tuple[ProductionTask, ...]]:
    """Create two persisted generated source objects and their published template and labels."""
    directory.mkdir(parents=True)
    paths: list[Path] = []
    for index in range(2):
        suffix = "txt" if kind == "text_span" else "jpg" if image_orientation else "png"
        path = directory / f"sample-{index}.{suffix}"
        if kind == "text_span":
            path.write_bytes("A猫\r\n nested text".encode())
        else:
            with Image.new("RGB", image_size, (30 + index, 80, 140)) as image:
                exif = Image.Exif()
                if image_orientation is not None:
                    exif[274] = image_orientation
                image.save(path, exif=exif)
        paths.append(path)
    dataset = import_paths(db, "Generated workbench", paths)
    version = list_versions(db, dataset.id)[0]
    run_action(
        db,
        "create_label_set",
        {"label_set_id": "wb-labels", "labels": [{"id": "cat", "name": "Cat"}]},
    )
    run_action(db, "publish_label_set", {"label_set_id": "wb-labels", "version": 1})
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "template": {"id": "wb-template", "name": "Workbench", "annotation_type": kind},
        },
    )
    project = Project.model_validate(
        run_action(
            db,
            "create_project",
            {
                "name": "Workbench",
                "dataset_id": dataset.id,
                "version_id": version.id,
                "label_set_id": "wb-labels",
                "template_id": "wb-template",
            },
        ).root
    )
    run_action(db, "split_packages", {"project_id": project.id, "package_size": package_size})
    return project, list_tasks(db, project.id)


def annotation_for(kind: ComponentKind, sample_id: str) -> AnnotationRecord:
    """Return attributed source-pixel geometry or nested character ranges for one component."""
    content = {
        "box": {
            "boxes": [
                {
                    "category": "Cat",
                    "x1": 1.5,
                    "y1": 2,
                    "x2": 30,
                    "y2": 50,
                    "attributes": {"occluded": True},
                }
            ]
        },
        "polygon": {
            "polygons": [
                {
                    "category": "Cat",
                    "points": [{"x": 1.5, "y": 2}, {"x": 30, "y": 4}, {"x": 20, "y": 40}],
                    "attributes": {"part": "tail"},
                }
            ]
        },
        "classification": {"labels": ["Cat"]},
        "text_span": {
            "text_length": 16,
            "spans": [
                {"category": "Cat", "start": 1, "end": 10, "attributes": {"nested": False}},
                {"category": "Cat", "start": 1, "end": 2, "attributes": {"nested": True}},
            ],
        },
    }
    return AnnotationRecord.model_validate(
        {
            "sample_id": sample_id,
            "annotator_id": "local",
            "attributes": {"quality": 4, "verified": True},
            **({"image_width": 100, "image_height": 80} if kind != "text_span" else {}),
            **content[kind],
        }
    )
