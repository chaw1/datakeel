# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Confidence tiers: calibration from approved data, per-project thresholds and routing."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from datakeel.actions.production_parameters import (
    ConfigureProjectParams,
    ReviewTaskParams,
    SaveRevisionParams,
)
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import ProductionTask
from datakeel.prelabel import use_transport
from datakeel.storage.action_rows import ActionAuditRow
from datakeel.storage.database import Database
from datakeel.storage.production_projects import configure_project
from datakeel.storage.production_queries import get_task, list_revisions
from datakeel.storage.production_reviews import review_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionReviewRow
from datakeel.storage.production_separation import require_separation
from datakeel.storage.production_tasks import require_project, require_task
from datakeel.storage.workbench_reads import workbench_project
from tests.prelabel_support import (
    CREDENTIAL_ENV,
    FIXTURE_CREDENTIAL,
    FakeVision,
    cloud_model,
    seed_cloud_project,
)
from tests.workbench_helpers import run_action

CALLER = AccessContext(actor="local", entry="ask", scope="query")


def _grid(count: int) -> list[AnnotationBox]:
    return [
        AnnotationBox(
            category="cat",
            x1=(index % 18) * 5,
            y1=(index // 18) * 5,
            x2=(index % 18) * 5 + 4,
            y2=(index // 18) * 5 + 4,
        )
        for index in range(count)
    ]


def _review(db: Database, task: ProductionTask, confidences: list[float], hits: list[bool]) -> None:
    """Store a model draft with per-object confidence, then approve a human head with hits."""
    boxes = _grid(len(confidences))
    record = AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="fixture",
        boxes=tuple(boxes),
        image_width=96,
        image_height=80,
    )
    with db.session() as session:
        model = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id=f"model-{task.id}",
                task_id=task.id,
                previous_revision_id=get_task(db, task.id).latest_revision_id,
                annotation=record,
                source="model",
                model_name="fixture",
                model_version="1",
                confidence=min(confidences),
                object_confidences=tuple(confidences),
            ),
            "local",
        )
        session.commit()
    human = record.model_copy(
        update={"boxes": tuple(box for box, hit in zip(boxes, hits, strict=True) if hit)}
    )
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": model.id,
            "annotation": human.model_dump(mode="json"),
        },
    )
    run_action(db, "submit_task", {"task_id": task.id})


def test_thresholds_are_back_calculated_from_approved_drafts(db: Database, tmp_path: Path) -> None:
    """Known per-band hit rates give high 0.95 and low 0.7 with each tier's measured rate."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=2)
    before = workbench_project(db, project.id, CALLER).confidence_thresholds
    assert before is not None
    assert (before.high, before.low, before.source) == (0.85, 0.5, "default")
    assert before.notes == ("insufficient_samples",)
    _review(db, tasks[0], [0.95] * 20, [True] * 20)
    _review(db, tasks[1], [0.7] * 10 + [0.3] * 8, [True] * 8 + [False] * 2 + [True] + [False] * 7)
    result = workbench_project(db, project.id, CALLER).confidence_thresholds
    assert result is not None
    assert (result.high, result.low, result.source, result.objects) == (0.95, 0.7, "calibrated", 38)
    rates = {tier.tier: (tier.objects, tier.hits) for tier in result.tiers}
    assert rates == {"high": (20, 20), "medium": (10, 8), "low": (8, 1)}
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.99})
    pinned = workbench_project(db, project.id, CALLER).confidence_thresholds
    assert pinned is not None
    assert (pinned.high, pinned.low, pinned.source) == (0.99, 0.7, "configured")
    run_action(
        db, "configure_project", {"project_id": project.id, "clear": ["confidence_thresholds"]}
    )
    cleared = workbench_project(db, project.id, CALLER).confidence_thresholds
    assert cleared is not None
    assert cleared.source == "calibrated"


def test_threshold_configuration_rejects_low_above_high(db: Database, tmp_path: Path) -> None:
    """Both in one request and across requests, low may never exceed high."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=1)
    with pytest.raises(ValueError, match="confidence_low"):
        ConfigureProjectParams(
            request_id="bad", project_id=project.id, confidence_high=0.5, confidence_low=0.6
        )
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.5})
    with pytest.raises(ValidationError, match="confidence_low"), db.session() as session:
        configure_project(
            session,
            ConfigureProjectParams(request_id="later", project_id=project.id, confidence_low=0.6),
        )


def _route(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tier: str,
    high: float | None = 0.9,
) -> tuple[PrelabelRun, dict[int, str]]:
    """Run a self-confidence cloud model over four images: high, medium, low and empty.

    ``high`` pins the project's high threshold; ``None`` leaves the cold-start defaults.
    """
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)
    project, _ = seed_cloud_project(db, tmp_path / tier, count=4, tier=tier)
    if high is not None:
        run_action(db, "configure_project", {"project_id": project.id, "confidence_high": high})
    run_action(db, "register_model", {"model": cloud_model(confidence_source="self")})
    fake = FakeVision(failures={3: "empty"}, confidence={0: 0.95, 1: 0.7, 2: 0.2})
    with use_transport(httpx.MockTransport(fake)):
        details = run_action(
            db, "run_prelabel", {"project_id": project.id, "model_id": "vision", "budget": 10}
        )
    run = PrelabelRun.model_validate(details.root)
    routed: dict[int, str] = {}
    for item in run.tiers:
        model = next(rev for rev in list_revisions(db, item.task_id) if rev.source == "model")
        width = model.annotation.image_width
        assert width is not None
        routed[(round(width) - 96) // 8] = item.routed
    return run, routed


def _pass_through_lines(db: Database) -> list[str]:
    with db.session() as session:
        rows = session.scalars(select(ActionAuditRow).where(ActionAuditRow.phase == "PRELABEL"))
        return [str(row.detail["message"]) for row in rows]


def test_group_tiers_route_high_to_review_medium_to_draft_low_to_scratch(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """High skips annotation into review, medium keeps the draft, low and empty start over."""
    run, routed = _route(db, tmp_path, monkeypatch, "group")
    assert routed == {0: "submitted", 1: "draft", 2: "scratch", 3: "scratch"}
    tiers = {tier.task_id: tier.tier for tier in run.tiers}
    states = sorted(get_task(db, task_id).state for task_id in tiers)
    assert states == ["pending", "pending", "pending", "submitted"]
    assert sorted(tiers.values()) == ["high", "low", "low", "medium"]
    assert run.thresholds is not None
    assert run.thresholds.source == "configured"


def test_pass_through_names_the_model_the_bar_and_the_person_who_ran_it(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The submitted draft stays model-sourced and the triggering person answers for it."""
    run, _ = _route(db, tmp_path, monkeypatch, "group")
    item = next(tier for tier in run.tiers if tier.routed == "submitted")
    task = get_task(db, item.task_id)
    assert task.annotator_id == "local"
    head = list_revisions(db, item.task_id)[-1]
    assert head.id == item.revision_id
    assert head.source == "model"
    assert head.pass_through is not None
    assert head.pass_through.model_dump() == {
        "model_id": "vision",
        "confidence": pytest.approx(0.95),
        "high": 0.9,
        "low": 0.5,
        "threshold_source": "configured",
        "reviewed_objects": 0,
        "triggered_by": "local",
    }
    lines = _pass_through_lines(db)
    assert len(lines) == 1
    assert lines[0].startswith("模型高置信度直通 / Model high-confidence pass-through: ")
    assert f"task={item.task_id}" in lines[0]
    assert "model=vision" in lines[0]
    assert "confidence=0.950; high=0.900; low=0.500" in lines[0]
    assert "triggered_by=local" in lines[0]


def test_cold_start_defaults_hold_high_drafts_for_a_person(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With default thresholds nothing passes through; the high draft waits, saying why."""
    run, routed = _route(db, tmp_path, monkeypatch, "group", high=None)
    assert run.thresholds is not None
    assert (run.thresholds.source, run.thresholds.pass_through) == ("default", False)
    assert routed == {0: "draft", 1: "draft", 2: "scratch", 3: "scratch"}
    held = next(tier for tier in run.tiers if tier.tier == "high")
    assert held.note == "insufficient_samples"
    assert {get_task(db, tier.task_id).state for tier in run.tiers} == {"pending"}
    assert not _pass_through_lines(db)


def test_team_pass_through_keeps_its_trigger_out_of_review(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In team projects the person who ran the model counts as annotator and cannot review."""
    run, _ = _route(db, tmp_path, monkeypatch, "team")
    item = next(tier for tier in run.tiers if tier.routed == "submitted")
    with db.session() as session:
        task = require_task(session, item.task_id)
        project = require_project(session, task.project_id)
        refused: AuthorizationError | None = None
        try:
            require_separation(session, project, task, "local")
        except AuthorizationError as error:
            refused = error
        assert refused is not None
        require_separation(session, project, task, "reviewer-2")


def test_personal_tiers_are_only_hints(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Personal projects keep every task with the annotator and only show the tier."""
    run, routed = _route(db, tmp_path, monkeypatch, "personal")
    assert set(routed.values()) == {"hint"}
    assert {get_task(db, tier.task_id).state for tier in run.tiers} == {"pending"}


def test_a_model_head_is_submitted_only_after_the_annotator_saves_it_as_their_own(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Submitting over a draft is refused with the reason; confirming it unchanged works."""
    run, _ = _route(db, tmp_path, monkeypatch, "personal")
    for item in run.tiers:
        head = list_revisions(db, item.task_id)[-1]
        assert head.source == "model"
        refused: ValidationError | None = None
        try:
            run_action(db, "submit_task", {"task_id": item.task_id})
        except ValidationError as error:
            refused = error
        assert refused is not None
        assert "Save it as your own revision first" in str(refused)
        run_action(
            db,
            "save_revision",
            {
                "task_id": item.task_id,
                "previous_revision_id": head.id,
                "annotation": head.annotation.model_copy(
                    update={"annotator_id": "local"}
                ).model_dump(mode="json"),
            },
        )
        run_action(db, "submit_task", {"task_id": item.task_id})
        assert get_task(db, item.task_id).state == "approved"


def test_review_of_a_pass_through_names_the_trigger_not_the_reviewer(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review row's annotator is who ran the model, even though nobody claimed the task."""
    run, _ = _route(db, tmp_path, monkeypatch, "group")
    item = next(tier for tier in run.tiers if tier.routed == "submitted")
    with db.session() as session:
        task = require_task(session, item.task_id)
        task.annotator_id = None  # A pass-through recorded before attribution existed.
        session.commit()
        review_task(
            session,
            ReviewTaskParams(
                request_id="review",
                task_id=item.task_id,
                revision_id=str(item.revision_id),
                decision="approve",
            ),
            "reviewer-2",
        )
        row = session.scalar(
            select(ProductionReviewRow).where(ProductionReviewRow.task_id == item.task_id)
        )
        assert row is not None
        assert row.annotator_id == "local"
