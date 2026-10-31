# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prelabel and AI pre-review on upright images, locked templates and handed-over rework.

Cloud drafts are display-frame revisions, so the model must see the upright pixels the
workbench shows. Accuracy and pre-review read a legacy stored-frame draft upright, both use the
template version the project is locked to, and whoever triggered a pass-through stays out of
review after its rework round is handed to someone else.
"""

from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageOps
from sqlalchemy import select

from datakeel.actions.production_parameters import AssignTasksParams, ReviewTaskParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import utcnow
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import AnnotationRevision, ProductionTask, Project
from datakeel.prelabel import use_transport
from datakeel.storage.database import Database
from datakeel.storage.production_ai_facts import load_facts
from datakeel.storage.production_assignments import assign_tasks, rework_transfers
from datakeel.storage.production_catalog import require_model, require_template
from datakeel.storage.production_cloud_prelabel import cloud_kinds
from datakeel.storage.production_queries import list_revisions
from datakeel.storage.production_reviews import review_task
from datakeel.storage.production_rows import ProductionRevisionRow, ProductionTaskRow
from datakeel.storage.production_separation import exclude_own_work, require_separation
from datakeel.storage.production_statistics import production_prelabel_accuracy
from datakeel.storage.production_tasks import require_project, require_task
from tests.prelabel_support import (
    CREDENTIAL_ENV,
    FIXTURE_CREDENTIAL,
    FakeVision,
    cloud_model,
    seed_cloud_project,
)
from tests.workbench_helpers import run_action

STORED_RED = (8.0, 10.0, 40.0, 50.0)  # The first generated image's rectangle, stored frame.


@pytest.fixture(autouse=True)
def _credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)


def _upright(path: Path) -> tuple[tuple[int, int], tuple[int, int, int, int]]:
    """Return the upright size and red-rectangle box a browser shows for a stored image."""
    with Image.open(path) as source:
        upright = ImageOps.exif_transpose(source)
    red = upright.getchannel("R").point([255 if value > 200 else 0 for value in range(256)])
    box = red.getbbox()
    assert box is not None
    return upright.size, box


def _run(db: Database, project: Project, fake: FakeVision | None = None) -> PrelabelRun:
    with use_transport(httpx.MockTransport(fake or FakeVision())):
        details = run_action(
            db, "run_prelabel", {"project_id": project.id, "model_id": "vision", "budget": 10}
        )
    return PrelabelRun.model_validate(details.root)


@pytest.mark.parametrize("orientation", range(1, 9))
def test_cloud_drafts_frame_the_upright_object_as_display_rows(
    db: Database, tmp_path: Path, orientation: int
) -> None:
    """The model sees the canvas pixels, so its box and size are upright and marked display."""
    project, (task,) = seed_cloud_project(db, tmp_path / "images", count=1, orientation=orientation)
    run_action(db, "register_model", {"model": cloud_model()})
    run = _run(db, project)
    assert (len(run.revision_ids), run.failures) == (1, ())
    size, expected = _upright(tmp_path / "images" / "rect-0.png")
    (draft,) = [item for item in list_revisions(db, task.id) if item.source == "model"]
    assert (draft.annotation.image_width, draft.annotation.image_height) == size
    [box] = list(draft.annotation.boxes or ())
    assert (box.x1, box.y1, box.x2, box.y2) == pytest.approx(expected, abs=1.5)
    assert draft.coordinate_conversion is None
    with db.session() as session:
        row = session.get(ProductionRevisionRow, draft.id)
        assert row is not None
        assert row.coordinate_frame == "display"


def _legacy_draft(db: Database, project: Project, task: ProductionTask) -> None:
    """Write a v0.18-style model draft: stored-frame box and no coordinate_frame marker."""
    revision = AnnotationRevision(
        id="legacy-draft",
        task_id=task.id,
        previous_revision_id=None,
        actor="local",
        created_at=utcnow(),
        source="model",
        model_name="fixture-vl",
        model_version="2026-10",
        confidence=0.9,
        annotation=AnnotationRecord(
            sample_id=task.sample_id,
            annotator_id="fixture-vl",
            image_width=96,
            image_height=80,
            boxes=(AnnotationBox(category="cat", x1=8, y1=10, x2=40, y2=50),),
        ),
    )
    with db.session() as session:
        session.add(
            ProductionRevisionRow(
                id=revision.id,
                task_id=task.id,
                project_id=project.id,
                source="model",
                actor="local",
                confidence=0.9,
                payload=revision.model_dump(mode="json"),
            )
        )
        row = session.get(ProductionTaskRow, task.id)
        assert row is not None
        row.latest_revision_id = revision.id
        session.commit()


def test_accuracy_and_pre_review_read_a_legacy_draft_upright(db: Database, tmp_path: Path) -> None:
    """A v0.18 draft on a rotated photo still matches the person's upright box exactly."""
    project, (task,) = seed_cloud_project(db, tmp_path / "images", count=1, orientation=6)
    _legacy_draft(db, project, task)
    size, upright = _upright(tmp_path / "images" / "rect-0.png")
    assert upright != STORED_RED
    human = AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="local",
        image_width=size[0],
        image_height=size[1],
        boxes=(
            AnnotationBox(
                category="cat", x1=upright[0], y1=upright[1], x2=upright[2], y2=upright[3]
            ),
        ),
    )
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": "legacy-draft",
            "annotation": human.model_dump(mode="json"),
        },
    )
    run_action(db, "submit_task", {"task_id": task.id})
    accuracy = production_prelabel_accuracy(db, project.id)
    assert (accuracy.assessed_tasks, accuracy.exact_match_tasks) == (1, 1)
    assert accuracy.iou_75.true_positives == 1
    with db.session() as session:
        stored = require_project(session, project.id)
        row = session.get(ProductionTaskRow, task.id)
        assert row is not None
        draft = load_facts(session, stored, row).tasks[task.id].draft
    assert draft is not None
    [box] = list(draft.record.boxes or ())
    assert (box.x1, box.y1, box.x2, box.y2) == upright


def test_cloud_kinds_and_pre_review_rules_follow_the_locked_template(
    db: Database, tmp_path: Path
) -> None:
    """A newer shared template revision changes neither what the model fills nor the rules."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=2, tier="group")
    run_action(db, "register_model", {"model": cloud_model()})
    config = {"components": ["box", "classification"], "exclusive_label_groups": [["cat", "dog"]]}
    with db.session() as session:
        current = require_template(session, "pl-template").model_dump(mode="json")
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "update",
            "template": {**current, "component_config": config},
        },
    )
    with db.session() as session:
        stored = require_project(session, project.id)
        assert stored.template_version == 1
        kinds = cloud_kinds(session, stored, require_model(session, "vision"))
        assert kinds == (frozenset({"box"}), False)
        row = session.get(ProductionTaskRow, tasks[0].id)
        assert row is not None
        facts = load_facts(session, stored, row)
    assert facts.template is not None
    assert facts.template.revision == 1
    assert "exclusive_label_groups" not in facts.template.component_config
    run = _run(db, project)
    assert (len(run.revision_ids), run.failures) == (2, ())
    for task in tasks:
        (draft,) = [item for item in list_revisions(db, task.id) if item.source == "model"]
        assert draft.annotation.labels is None


def test_pass_through_trigger_stays_out_of_review_after_a_rework_handover(
    db: Database, tmp_path: Path
) -> None:
    """Handing the rework to someone else changes the annotator, not who answered for it."""
    project, (task,) = seed_cloud_project(db, tmp_path / "images", count=1, tier="team")
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.9})
    run_action(db, "register_model", {"model": cloud_model(confidence_source="self")})
    run = _run(db, project, FakeVision(confidence=0.95))
    (item,) = run.tiers
    assert item.routed == "submitted"
    with db.session() as session:
        review_task(
            session,
            ReviewTaskParams(
                request_id="rework",
                task_id=task.id,
                revision_id=str(item.revision_id),
                decision="rework",
                issues=("The box misses the tail",),
            ),
            "reviewer-2",
        )
        session.commit()
    with db.session() as session:
        transfers = rework_transfers([require_task(session, task.id)], "ann-b")
        assert [(move.from_actor, move.to_actor) for move in transfers] == [("local", "ann-b")]
        assign_tasks(
            session,
            AssignTasksParams(
                request_id="handover", task_ids=(task.id,), actor="ann-b", transfers=transfers
            ),
        )
        session.commit()
    with db.session() as session:
        row = require_task(session, task.id)
        stored = require_project(session, project.id)
        assert row.annotator_id == "ann-b"
        query = select(ProductionTaskRow).where(ProductionTaskRow.id == task.id)
        queues = {
            person: session.scalar(exclude_own_work(query, person)) is not None
            for person in ("local", "ann-b", "reviewer-2")
        }
        assert queues == {"local": False, "ann-b": False, "reviewer-2": True}
        refused: list[str] = []
        for person in ("local", "ann-b", "reviewer-2"):
            try:
                require_separation(session, stored, row, person)
            except AuthorizationError:
                refused.append(person)
        assert refused == ["local", "ann-b"]
