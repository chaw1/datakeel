# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate local workbench browser fixtures or serve their isolated API on port 8840."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import uvicorn
from PIL import Image, ImageDraw
from sqlalchemy import event, text
from sqlalchemy.engine import make_url

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import BoundaryModel, JsonDocument, new_id
from datakeel.core.production_models import Project
from datakeel.core.settings import get_settings
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_queries import list_tasks

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

ComponentKind = Literal["box", "polygon", "classification", "text_span"]


class FixtureProject(BoundaryModel):
    """Return public production identities and decoded image dimensions to browser scripts."""

    project_id: str
    task_ids: tuple[str, ...]
    image_width: int | None = None
    image_height: int | None = None


def _run(db: Database, action: str, values: Mapping[str, object]) -> JsonDocument:
    body = JsonDocument.model_validate({"request_id": new_id(), **values})
    plan = prepare_action(db, action, body, ActionContext(actor="local"))
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if result.status != "SUCCEEDED" or result.receipt is None:
        message = f"Generated fixture action failed: {action}"
        raise RuntimeError(message)
    return JsonDocument.model_validate(result.receipt.quality["details"])


def _source(directory: Path, kind: ComponentKind, size: tuple[int, int], count: int) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for index in range(count):
        path = directory / f"sample-{index:03d}.{'txt' if kind == 'text_span' else 'png'}"
        if kind == "text_span":
            path.write_text(
                "猫 and dog share a generated annotation example. " * 12, encoding="utf-8"
            )
        else:
            with Image.new("RGB", size, (28 + index * 3, 72, 118)) as image:
                draw = ImageDraw.Draw(image)
                draw.rectangle(
                    (100, 100, min(size[0] - 1, 800), min(size[1] - 1, 700)),
                    fill=(170, 100 + index, 65),
                )
                draw.text((130, 130), f"Generated sample {index}", fill=(240, 240, 240))
                image.save(path)
        result.append(path)
    return result


def _annotation(kind: ComponentKind, sample_id: str, size: tuple[int, int]) -> AnnotationRecord:
    content: dict[ComponentKind, dict[str, object]] = {
        "box": {
            "boxes": [
                {
                    "category": "cat",
                    "x1": 100,
                    "y1": 100,
                    "x2": 800,
                    "y2": 700,
                    "attributes": {"visible": True},
                }
            ]
        },
        "polygon": {
            "polygons": [
                {
                    "category": "cat",
                    "points": [{"x": 100, "y": 100}, {"x": 800, "y": 100}, {"x": 500, "y": 700}],
                    "attributes": {"visible": True},
                }
            ]
        },
        "classification": {"labels": ["cat"]},
        "text_span": {
            "spans": [
                {"category": "cat", "start": 0, "end": 9},
                {"category": "cat", "start": 0, "end": 1},
            ],
            "text_length": len("猫 and dog share a generated annotation example. " * 12),
        },
    }
    return AnnotationRecord.model_validate(
        {
            "sample_id": sample_id,
            "annotator_id": "local",
            **({"image_width": size[0], "image_height": size[1]} if kind != "text_span" else {}),
            **content[kind],
        }
    )


def _project(
    db: Database,
    directory: Path,
    label_set_id: str,
    definition: tuple[str, ComponentKind, tuple[int, int], int],
) -> FixtureProject:
    name, kind, size, count = definition
    dataset = import_paths(db, f"Workbench {name}", _source(directory / name, kind, size, count))
    version = list_versions(db, dataset.id)[0]
    template_id = new_id()
    _run(
        db,
        "create_label_set",
        {
            "target": "template",
            "template": {
                "id": template_id,
                "name": name,
                "annotation_type": kind,
                "component_config": {"label_mode": "multi"},
            },
        },
    )
    project = Project.model_validate(
        _run(
            db,
            "create_project",
            {
                "name": f"Workbench {name}",
                "dataset_id": dataset.id,
                "version_id": version.id,
                "label_set_id": label_set_id,
                "template_id": template_id,
                "guidelines": "Use source coordinates and the published labels.",
            },
        ).root
    )
    _run(db, "split_packages", {"project_id": project.id, "package_size": 100})
    tasks = list_tasks(db, project.id)
    for task in tasks:
        _run(
            db,
            "save_revision",
            {
                "task_id": task.id,
                "previous_revision_id": None,
                "annotation": _annotation(kind, task.sample_id, size).model_dump(mode="json"),
            },
        )
    return FixtureProject(
        project_id=project.id,
        task_ids=tuple(task.id for task in tasks),
        image_width=size[0] if kind != "text_span" else None,
        image_height=size[1] if kind != "text_span" else None,
    )


def generate(db: Database, directory: Path) -> JsonDocument:
    """Generate a fresh set without removing or rewriting any existing user's objects."""
    labels = new_id()
    _run(
        db,
        "create_label_set",
        {
            "label_set_id": labels,
            "name": "Workbench labels",
            "labels": [
                {"id": "cat", "name": "Cat", "shortcut": "1", "color": "#d96d32"},
                {"id": "dog", "name": "Dog", "shortcut": "2", "color": "#2779bd"},
            ],
        },
    )
    _run(db, "publish_label_set", {"label_set_id": labels, "version": 1})
    definitions: tuple[tuple[str, ComponentKind, tuple[int, int], int], ...] = (
        ("box", "box", (2000, 1500), 24),
        ("polygon", "polygon", (2000, 1500), 4),
        ("classification", "classification", (2000, 1500), 4),
        ("text_span", "text_span", (0, 0), 4),
        ("large4k", "box", (3840, 2160), 1),
        ("large8k", "box", (8000, 6000), 1),
    )
    projects = {
        definition[0]: _project(db, directory, labels, definition).model_dump(mode="json")
        for definition in definitions
    }
    return JsonDocument.model_validate({"actor": "local", "projects": projects})


def _database(schema: str, *, use_test_database: bool) -> Database:
    if get_settings().s3_bucket is not None:
        message = "Generated workbench fixtures require local object storage"
        raise ValueError(message)
    if not use_test_database:
        url = get_settings().database_url or f"sqlite:///{data_dir() / 'datakeel.db'}"
        if not make_url(url).drivername.startswith("sqlite"):
            message = "Non-SQLite fixtures require the authorized local test wrapper"
            raise ValueError(message)
        return Database(url)
    url = get_settings().test_database_url or ""
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or not parsed.drivername.startswith(
        "postgresql"
    ):
        message = "Fixture PostgreSQL must be selected by the authorized local test wrapper"
        raise ValueError(message)
    if re.fullmatch(r"p30_[a-z0-9_]+", schema) is None:
        message = "Use an isolated p30_ schema name"
        raise ValueError(message)
    db = Database(url)
    with db.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    db.engine.dispose()

    @event.listens_for(db.engine, "connect")
    def select_schema(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
        cursor = connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()
        cursor.close()

    return db


def main() -> None:
    """Create the reusable manifest or run its API against the same explicitly chosen store."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--test-database", action="store_true")
    parser.add_argument("--schema", default="p30_workbench")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    db = _database(args.schema, use_test_database=args.test_database)
    try:
        db.migrate()
        if args.serve:
            uvicorn.run(create_app(db), host="127.0.0.1", port=8840)
        elif args.output and args.source_dir:
            output = generate(db, args.source_dir)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output.model_dump_json(indent=2) + "\n", encoding="utf-8")
        else:
            parser.error("Generation requires --output and --source-dir")
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
