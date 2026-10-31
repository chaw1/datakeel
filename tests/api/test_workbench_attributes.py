# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Template attribute fields are enforced on direct saves and submissions over HTTP."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.api.app import create_app
from datakeel.core.errors import ValidationError
from datakeel.core.models import new_id
from datakeel.storage.production_catalog import require_template
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from tests.asgi_client import TestClient
from tests.production_team_ops import failure
from tests.workbench_helpers import annotation_for, run_action, seed_workbench

if TYPE_CHECKING:
    from pathlib import Path

    from httpx import Response
    from pydantic import JsonValue

    from datakeel.core.production_catalog_models import ProductionTemplate
    from datakeel.storage.database import Database

CHOICES: list[JsonValue] = [
    {"value": "car", "name_zh": "轿车", "name_en": "Car"},
    {"value": "bus", "name_zh": "公交", "name_en": "Bus"},
]
FIELDS: list[JsonValue] = [
    {"key": "occluded", "name_zh": "遮挡", "name_en": "Occluded", "type": "boolean"},
    {
        "key": "kind",
        "name_zh": "类型",
        "name_en": "Kind",
        "type": "enum",
        "options": CHOICES,
        "required": True,
    },
    {"key": "tags", "name_zh": "标签", "name_en": "Tags", "type": "multi_enum", "options": CHOICES},
    {
        "key": "count",
        "name_zh": "数量",
        "name_en": "Count",
        "type": "number",
        "minimum": 0,
        "maximum": 10,
    },
    {"key": "note", "name_zh": "备注", "name_en": "Note", "type": "text", "max_length": 5},
    {
        "key": "quality",
        "name_zh": "质量",
        "name_en": "Quality",
        "type": "enum",
        "options": CHOICES,
        "target": "record",
        "required": True,
        "default": "car",
    },
]


def _configure(db: Database, fields: list[JsonValue], project_id: str) -> ProductionTemplate:
    """Save a new template version, then sign the project's upgrade onto it (TAILS-4 R1)."""
    with db.session() as session:
        current = require_template(session, "wb-template")
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "update",
            "template": {
                "id": "wb-template",
                "name": "Workbench",
                "annotation_type": "box",
                "revision": current.revision,
                "attributes": fields,
            },
        },
    )
    run_action(db, "upgrade_project_template", {"project_id": project_id})
    with db.session() as session:
        return require_template(session, "wb-template")


def _save(
    client: TestClient, task_id: str, annotation: JsonValue, previous: str | None
) -> Response:
    prepared = client.post(
        "/api/actions/save_revision/prepare",
        json={
            "request_id": new_id(),
            "task_id": task_id,
            "previous_revision_id": previous,
            "annotation": annotation,
        },
    )
    assert prepared.status_code == 200, prepared.text
    plan = prepared.json()
    return client.post(
        f"/api/actions/{plan['id']}/execute",
        json={"plan_digest": plan["plan_digest"], "actor": "local"},
    )


def _annotation(
    sample_id: str, box: dict[str, JsonValue], record: dict[str, JsonValue]
) -> JsonValue:
    annotation = annotation_for("box", sample_id)
    boxes = tuple(item.model_copy(update={"attributes": box}) for item in annotation.boxes or ())
    updated = annotation.model_copy(update={"boxes": boxes, "attributes": record})
    return updated.model_dump(mode="json")


def test_direct_saves_name_the_failing_attribute_with_http_422(
    db: Database, tmp_path: Path
) -> None:
    """Missing, out-of-range and record-level fields are rejected with their key; valid saves."""
    project, tasks = seed_workbench(db, tmp_path / "attributes")
    template = _configure(db, FIELDS, project.id)
    assert [field.key for field in template.attributes] == [
        "occluded",
        "kind",
        "tags",
        "count",
        "note",
        "quality",
    ]
    task = tasks[0]
    valid: dict[str, JsonValue] = {
        "occluded": True,
        "kind": "bus",
        "tags": ["car"],
        "count": 3,
        "note": "ok",
    }
    cases: tuple[tuple[dict[str, JsonValue], dict[str, JsonValue], str], ...] = (
        ({**valid, "kind": None}, {"quality": "car"}, 'Attribute \\"kind\\" is required on box 1'),
        (
            {**valid, "count": 11},
            {"quality": "car"},
            'Attribute \\"count\\" on box 1 must be a number between 0 and 10',
        ),
        ({**valid, "note": "toolong"}, {"quality": "car"}, 'Attribute \\"note\\" on box 1'),
        ({**valid, "tags": ["car", "car"]}, {"quality": "car"}, 'Attribute \\"tags\\" on box 1'),
        ({**valid, "occluded": "yes"}, {"quality": "car"}, 'Attribute \\"occluded\\" on box 1'),
        (valid, {}, 'Attribute \\"quality\\" is required on the record'),
    )
    with TestClient(create_app(db)) as client:
        for box, record, expected in cases:
            rejected = _save(client, task.id, _annotation(task.sample_id, box, record), None)
            assert rejected.status_code == 422, rejected.text
            assert expected in rejected.text
        saved = _save(client, task.id, _annotation(task.sample_id, valid, {"quality": "car"}), None)
        assert saved.status_code == 200, saved.text
        assert saved.json()["status"] == "SUCCEEDED"


def test_submission_rechecks_the_head_against_a_newer_required_field(
    db: Database, tmp_path: Path
) -> None:
    """A head saved before a field became required cannot be submitted until it is filled."""
    project, tasks = seed_workbench(db, tmp_path / "submit")
    task = tasks[0]
    with TestClient(create_app(db)) as client:
        saved = _save(client, task.id, _annotation(task.sample_id, {"occluded": True}, {}), None)
        assert saved.status_code == 200, saved.text
        _configure(db, FIELDS[:2], project.id)
        prepared = client.post(
            "/api/actions/submit_task/prepare", json={"request_id": new_id(), "task_id": task.id}
        )
        assert prepared.status_code == 200, prepared.text
        plan = prepared.json()
        rejected = client.post(
            f"/api/actions/{plan['id']}/execute",
            json={"plan_digest": plan["plan_digest"], "actor": "local"},
        )
        assert rejected.status_code == 422, rejected.text
        assert 'Attribute \\"kind\\" is required on box 1' in rejected.text


def test_old_templates_keep_saving_arbitrary_attributes(db: Database, tmp_path: Path) -> None:
    """Without defined fields the attribute dictionary stays free-form, as before."""
    _, tasks = seed_workbench(db, tmp_path / "legacy")
    task = tasks[0]
    with TestClient(create_app(db)) as client:
        free = _annotation(task.sample_id, {"anything": [1, {"x": None}]}, {"misc": "kept"})
        saved = _save(client, task.id, free, None)
        assert saved.status_code == 200, saved.text


def test_model_drafts_skip_required_fields_but_not_their_types(
    db: Database, tmp_path: Path
) -> None:
    """A prediction may leave a field for the annotator, but cannot store a wrong type."""
    project, tasks = seed_workbench(db, tmp_path / "model")
    _configure(db, FIELDS, project.id)
    task = tasks[0]

    def model_save(box: dict[str, JsonValue]) -> None:
        annotation = annotation_for("box", task.sample_id).model_copy(update={"attributes": {}})
        boxes = annotation.boxes or ()
        annotation = annotation.model_copy(
            update={"boxes": tuple(item.model_copy(update={"attributes": box}) for item in boxes)}
        )
        with db.session() as session:
            db.lock_writes(session)
            row = require_task(session, task.id)
            append_revision(
                session,
                row,
                SaveRevisionParams(
                    request_id=new_id(),
                    task_id=task.id,
                    previous_revision_id=row.latest_revision_id,
                    annotation=annotation,
                    source="model",
                    model_name="fake",
                    model_version="1",
                    confidence=0.5,
                ),
                "model",
            )
            session.commit()

    assert failure(lambda: model_save({})) is None
    error = failure(lambda: model_save({"count": "many"}))
    assert isinstance(error, ValidationError)
    assert 'Attribute "count" on box 1' in str(error)
