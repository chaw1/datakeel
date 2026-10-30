# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cloud prelabel through the real controlled action against a recorded fake vision server."""

import logging
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, text

from datakeel.actions.models import ActionContext
from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.actions.service import prepare_action
from datakeel.core.errors import ValidationError
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import AnnotationRevision
from datakeel.prelabel import use_transport
from datakeel.storage.database import Base, Database
from datakeel.storage.production_catalog_plans import catalog_manifest, catalog_requires_approval
from datakeel.storage.production_predictions import run_prelabel
from datakeel.storage.production_rows import ProductionRevisionRow
from tests.prelabel_support import (
    CREDENTIAL_ENV,
    FIXTURE_CREDENTIAL,
    FakeVision,
    cloud_model,
    seed_cloud_project,
)
from tests.production_flow_support import action_payload
from tests.workbench_helpers import run_action

PER_CALL = (400 * 0.2 + 50 * 2.0) / 1000


@pytest.fixture
def credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose the fixture credential only through the configured environment variable."""
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)


def _run(db: Database, project_id: str, fake: FakeVision, budget: float = 100) -> PrelabelRun:
    with use_transport(httpx.MockTransport(fake)):
        details = run_action(
            db, "run_prelabel", {"project_id": project_id, "model_id": "vision", "budget": budget}
        )
    return PrelabelRun.model_validate(details.root)


def _model_revisions(db: Database) -> list[AnnotationRevision]:
    with db.session() as session:
        rows = session.scalars(
            select(ProductionRevisionRow).where(ProductionRevisionRow.source == "model")
        )
        return [AnnotationRevision.model_validate(row.payload) for row in rows]


@pytest.mark.usefixtures("credential")
def test_cloud_run_boxes_every_image_and_accounts_each_call(db: Database, tmp_path: Path) -> None:
    """Both views are sent, boxes land on the rectangle in source pixels, costs are measured."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=3)
    run_action(db, "register_model", {"model": cloud_model()})
    fake = FakeVision()
    run = _run(db, project.id, fake)
    assert len(run.revision_ids) == len(tasks)
    assert len(fake.requests) == 6
    assert all(body["enable_thinking"] is False for body in fake.requests)
    assert (run.input_tokens, run.output_tokens) == (2400, 300)
    assert run.cost == pytest.approx(6 * PER_CALL)
    assert {call.view for call in run.calls} == {"primary", "mirrored"}
    assert run.estimate is not None
    assert run.estimate.images == 3
    assert run.stopped is None
    assert run.provider == "cloud"
    assert run.currency == "CNY"
    by_sample = {revision.annotation.sample_id: revision for revision in _model_revisions(db)}
    for task in tasks:
        annotation = by_sample[task.sample_id].annotation
        assert annotation.image_width is not None
        index = (round(annotation.image_width) - 96) // 8
        boxes = annotation.boxes
        assert boxes is not None
        assert len(boxes) == 1
        box = boxes[0]
        assert box.category == "cat"
        assert box.x1 == pytest.approx(8 + index, abs=1.5)
        assert box.x2 == pytest.approx(40 + index, abs=1.5)
        assert (box.y1, box.y2) == (pytest.approx(10, abs=1.5), pytest.approx(50, abs=1.5))
    confidences = by_sample[tasks[0].sample_id].object_confidences
    assert len(confidences) == 1
    assert confidences[0] == pytest.approx((0.9 + 1.0) / 2, abs=0.05)
    assert by_sample[tasks[0].sample_id].confidence_tier == "high"


@pytest.mark.usefixtures("credential")
def test_budget_stops_mid_run_and_rerun_only_fills_unrun_images(
    db: Database, tmp_path: Path
) -> None:
    """An estimate above budget needs approval; execution stops and the rerun never repays."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=4)
    run_action(db, "register_model", {"model": cloud_model()})
    params = RunPrelabelParams(request_id="estimate", project_id=project.id, model_id="vision")
    with db.session() as session:
        estimate = catalog_manifest(session, params).objects[-len(tasks) - 1]
        assert estimate.asset_ref.asset_type == "prelabel_estimate"
        per_image = float(str(estimate.properties["per_image"]))
        assert catalog_requires_approval(session, params.model_copy(update={"budget": 1}))
        assert not catalog_requires_approval(session, params.model_copy(update={"budget": 2}))
    plan = prepare_action(
        db,
        "run_prelabel",
        action_payload(
            "run_prelabel",
            {"project_id": project.id, "model_id": "vision", "budget": per_image * 2.5},
        ),
        ActionContext(actor="local"),
    )
    assert plan.requires_approval
    fake = FakeVision()
    first = _run(db, project.id, fake, budget=per_image * 2.5)
    assert len(first.revision_ids) == 2
    assert first.stopped is not None
    assert (first.stopped.completed_images, first.stopped.remaining_images) == (2, 2)
    assert first.stopped.spent == pytest.approx(first.cost)
    assert first.cost <= per_image * 2.5
    stopped_at = first.stopped.before_sample_id
    second = _run(db, project.id, fake)
    assert len(second.revision_ids) == 2
    assert len(fake.requests) == 8
    assert sorted(second.skipped_sample_ids) == sorted(tier.sample_id for tier in first.tiers)
    assert stopped_at in {tier.sample_id for tier in second.tiers}
    third = _run(db, project.id, fake, budget=0)
    assert (third.revision_ids, third.cost, len(fake.requests)) == ((), 0, 8)
    assert third.estimate is not None
    assert (third.estimate.images, third.estimate.total) == (0, 0)


@pytest.mark.usefixtures("credential")
def test_failure_list_names_each_class_and_rerun_retries_only_failures(
    db: Database, tmp_path: Path
) -> None:
    """Timeouts, rate limits, outages, server errors and prose fail per image, then recover."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=6)
    run_action(db, "register_model", {"model": cloud_model()})
    script = {1: "timeout", 2: "429", 3: "network", 4: "500", 5: "prose"}
    first = _run(db, project.id, FakeVision(failures=script))
    assert len(first.revision_ids) == 1
    codes = sorted(failure.code for failure in first.failures)
    assert codes == sorted(
        ["timeout", "rate_limited", "network_error", "provider_error_500", "invalid_response"]
    )
    assert all("scripted" not in failure.message for failure in first.failures)
    assert first.cost == pytest.approx(4 * PER_CALL)
    recovered = FakeVision()
    second = _run(db, project.id, recovered)
    assert len(second.revision_ids) == 5
    assert len(recovered.requests) == 10
    assert not second.failures


def test_missing_credential_fails_before_any_request(db: Database, tmp_path: Path) -> None:
    """Without the named variable nothing is sent and nothing is written."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=2)
    run_action(db, "register_model", {"model": cloud_model()})
    fake = FakeVision()
    params = RunPrelabelParams(request_id="nokey", project_id=project.id, model_id="vision")
    with (
        use_transport(httpx.MockTransport(fake)),
        db.session() as session,
        pytest.raises(ValidationError, match=CREDENTIAL_ENV),
    ):
        run_prelabel(session, params.model_copy(update={"budget": 10}), "local")
    assert not fake.requests
    assert not _model_revisions(db)


@pytest.mark.usefixtures("credential")
def test_credential_reaches_only_the_authorization_header(
    db: Database, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The secret is sent as a bearer token and appears in no row, receipt or log line."""
    caplog.set_level(logging.DEBUG)
    project, _ = seed_cloud_project(db, tmp_path / "images", count=2)
    run_action(db, "register_model", {"model": cloud_model()})
    fake = FakeVision(failures={1: "500"})
    run = _run(db, project.id, fake)
    assert set(fake.authorizations) == {f"Bearer {FIXTURE_CREDENTIAL}"}
    assert FIXTURE_CREDENTIAL not in run.model_dump_json()
    assert FIXTURE_CREDENTIAL not in caplog.text
    with db.session() as session:
        for table in Base.metadata.sorted_tables:
            rows = session.execute(text(f'SELECT * FROM "{table.name}"')).all()  # noqa: S608
            assert FIXTURE_CREDENTIAL not in repr(rows), table.name


@pytest.mark.usefixtures("credential")
def test_missing_usage_is_priced_from_the_estimate(db: Database, tmp_path: Path) -> None:
    """A provider that omits usage is still charged, at the estimated tokens, never at zero."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=1)
    run_action(db, "register_model", {"model": cloud_model()})
    run = _run(db, project.id, FakeVision(usage=None))
    assert run.cost > 0
    assert run.estimate is not None
    assert run.cost == pytest.approx(run.estimate.total)
