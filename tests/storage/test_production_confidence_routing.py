# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Confidence tiers: calibration from approved data, per-project thresholds and routing."""

from pathlib import Path

import httpx
import pytest

from datakeel.actions.production_parameters import ConfigureProjectParams, SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ValidationError
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import ProductionTask
from datakeel.prelabel import use_transport
from datakeel.storage.database import Database
from datakeel.storage.production_projects import configure_project
from datakeel.storage.production_queries import get_task, list_revisions
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
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
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tier: str
) -> tuple[PrelabelRun, dict[int, str]]:
    """Run a self-confidence cloud model over four images: high, medium, low and empty."""
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)
    project, _ = seed_cloud_project(db, tmp_path / tier, count=4, tier=tier)
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
    assert run.thresholds.source == "default"


def test_personal_tiers_are_only_hints(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Personal projects keep every task with the annotator and only show the tier."""
    run, routed = _route(db, tmp_path, monkeypatch, "personal")
    assert set(routed.values()) == {"hint"}
    assert {get_task(db, tier.task_id).state for tier in run.tiers} == {"pending"}
