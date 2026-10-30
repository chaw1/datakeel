# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cloud runs call the model outside every transaction, one live run per project, readable."""

import threading
import time
import warnings
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import ConflictError
from datakeel.core.models import utcnow
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import ProductionTask
from datakeel.prelabel import use_transport
from datakeel.storage.action_rows import ActionRunRow
from datakeel.storage.action_worker import reconcile_runs
from datakeel.storage.database import Database
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
from datakeel.storage.production_predictions import run_prelabel
from datakeel.storage.production_prelabel_reads import prelabel_progress
from datakeel.storage.production_prelabel_runs import STALE_AFTER, locked_run, store_run
from datakeel.storage.production_queries import list_revisions
from tests.prelabel_support import (
    CREDENTIAL_ENV,
    FIXTURE_CREDENTIAL,
    FakeVision,
    cloud_model,
    seed_cloud_project,
)
from tests.production_flow_support import action_payload
from tests.workbench_helpers import run_action

if TYPE_CHECKING:
    from datakeel.core.prelabel_models import PrelabelProgress

pytestmark = pytest.mark.usefixtures("credential")


@pytest.fixture
def credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose the fixture credential only through the configured environment variable."""
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)


def _values(project_id: str, budget: float = 100) -> dict[str, object]:
    return {"project_id": project_id, "model_id": "vision", "budget": budget}


class ProbingVision(FakeVision):
    """While the fifth image is in flight, write elsewhere and read this run's progress."""

    def __init__(self, db: Database, project_id: str, other_project_id: str) -> None:
        """Probe once, from inside the provider call, so no runner code is between."""
        super().__init__(failures={1: "500"})
        self.db, self.project_id, self.other = db, project_id, other_project_id
        self.write_seconds: float | None = None
        self.progress: tuple[PrelabelProgress, ...] = ()
        self.reconciled: int | None = None
        self.warnings: list[str] = []
        self._probe = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Answer as usual; the first call of the second batch probes the database first."""
        with self._probe:
            probing = len(self.requests) == 8 and self.write_seconds is None
            if probing:
                started = time.perf_counter()
                run_action(
                    self.db, "configure_project", {"project_id": self.other, "confidence_high": 0.9}
                )
                self.write_seconds = time.perf_counter() - started
                self.progress = prelabel_progress(self.db, self.project_id)
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    self.reconciled = reconcile_runs(self.db)
                self.warnings = [str(item.message) for item in caught]
        return super().__call__(request)


def test_model_calls_hold_no_lock_and_progress_is_readable_mid_run(
    db: Database, tmp_path: Path
) -> None:
    """Another project's write finishes at once mid-run; done, failed and spent are visible."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=8)
    other = run_action(
        db,
        "create_project",
        {
            "name": "Other",
            "dataset_id": project.dataset_id,
            "version_id": project.version_id,
            "label_set_id": "pl-labels",
            "template_id": "pl-template",
            "workflow_tier": "group",
        },
    ).root
    assert isinstance(other, dict)
    run_action(db, "register_model", {"model": cloud_model()})
    fake = ProbingVision(db, project.id, str(other["id"]))
    with use_transport(httpx.MockTransport(fake)):
        details = run_action(db, "run_prelabel", _values(project.id))
    assert fake.write_seconds is not None
    assert fake.write_seconds < 1
    # The worker's reconciler leaves the live run, which has no worker task, to its caller.
    assert (fake.reconciled, fake.warnings) == (0, [])
    (running,) = fake.progress
    assert (running.status, running.planned_images) == ("running", 8)
    # Tasks run in id order, so the scripted failure may fall in either batch.
    assert running.completed_images + running.failed_images == 4
    assert running.spent > 0
    final = PrelabelRun.model_validate(details.root)
    assert (final.status, final.completed_images, final.failed_images) == ("completed", 7, 1)
    (done,) = prelabel_progress(db, project.id)
    assert (done.status, done.completed_images, done.spent) == ("completed", 7, final.cost)


def test_failures_name_the_file_and_keep_the_sample_apart(db: Database, tmp_path: Path) -> None:
    """The failure list shows the image's file name; the sample id has its own field."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=2)
    run_action(db, "register_model", {"model": cloud_model()})
    with use_transport(httpx.MockTransport(FakeVision(failures={1: "timeout"}))):
        details = run_action(db, "run_prelabel", _values(project.id))
    (failure,) = PrelabelRun.model_validate(details.root).failures
    assert failure.filename == "rect-1.png"
    assert failure.sample_id in {task.sample_id for task in tasks}
    assert failure.sample_id != failure.filename


def test_a_second_live_run_on_the_project_is_refused_until_the_first_goes_silent(
    db: Database, tmp_path: Path
) -> None:
    """Only one run may spend on a project; a run silent past the limit is taken over."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=2)
    run_action(db, "register_model", {"model": cloud_model()})
    params = RunPrelabelParams(request_id="first", project_id=project.id, model_id="vision")
    with db.session() as session:
        first = run_prelabel(session, params.model_copy(update={"budget": 10}), "local")
        session.commit()
    fake = FakeVision()
    refused: ConflictError | None = None
    with use_transport(httpx.MockTransport(fake)):
        try:
            run_action(db, "run_prelabel", _values(project.id))
        except ConflictError as error:
            refused = error
    assert refused is not None
    assert "already in progress" in str(refused)
    assert not fake.requests
    with db.session() as session:
        row, run = locked_run(session, first.id)
        store_run(row, run.model_copy(update={"updated_at": utcnow() - STALE_AFTER * 2}))
        session.commit()
    with use_transport(httpx.MockTransport(fake)):
        second = PrelabelRun.model_validate(
            run_action(db, "run_prelabel", _values(project.id)).root
        )
    assert len(second.revision_ids) == 2
    with db.session() as session:
        _, abandoned = locked_run(session, first.id)
    assert abandoned.status == "abandoned"


class TakeoverVision(FakeVision):
    """Mark the run abandoned while its first batch is at the provider."""

    def __init__(self, db: Database) -> None:
        """Remember the database so the first call can take the run over."""
        super().__init__()
        self.db = db
        self._once = threading.Lock()
        self.done = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Abandon every running run once, then answer normally."""
        with self._once:
            if not self.done:
                self.done = True
                with self.db.session() as session:
                    for row in session.scalars(select(ProductionPrelabelRunRow)):
                        run = PrelabelRun.model_validate(row.payload)
                        store_run(row, run.model_copy(update={"status": "abandoned"}))
                    session.commit()
        return super().__call__(request)


def test_a_run_taken_over_writes_nothing_more_and_fails_its_action(
    db: Database, tmp_path: Path
) -> None:
    """Results arriving after a takeover are not written, and no further image is sent."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=6)
    run_action(db, "register_model", {"model": cloud_model()})
    plan = prepare_action(
        db, "run_prelabel", action_payload("run_prelabel", _values(project.id)), ActionContext()
    )
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    fake = TakeoverVision(db)
    with use_transport(httpx.MockTransport(fake)):
        run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "FAILED"
    assert run.error is not None
    assert "took over" in run.error
    assert len(fake.requests) == 8  # One batch of four images, two views each.
    with db.session() as session:
        (row,) = session.scalars(select(ProductionPrelabelRunRow))
        assert PrelabelRun.model_validate(row.payload).revision_ids == ()
        status = session.scalar(select(ActionRunRow.status).where(ActionRunRow.id == run.id))
    assert status == "FAILED"


class EditingVision(FakeVision):
    """While the first batch is at the provider, a person saves their own work on every task."""

    def __init__(self, db: Database, tasks: tuple[ProductionTask, ...]) -> None:
        """Remember the tasks a person edits on the first call."""
        super().__init__()
        self.db, self.tasks = db, tasks
        self._once = threading.Lock()
        self.done = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Save one human revision per task once, then answer normally."""
        with self._once:
            if not self.done:
                self.done = True
                for task in self.tasks:
                    box = AnnotationBox(category="cat", x1=1, y1=2, x2=30, y2=50)
                    record = AnnotationRecord(
                        sample_id=task.sample_id, annotator_id="local", boxes=(box,)
                    )
                    run_action(
                        self.db,
                        "save_revision",
                        {
                            "task_id": task.id,
                            "previous_revision_id": None,
                            "annotation": record.model_dump(mode="json"),
                        },
                    )
        return super().__call__(request)


def test_a_draft_never_lands_on_work_a_person_saved_while_the_model_ran(
    db: Database, tmp_path: Path
) -> None:
    """Results for edited tasks are paid for and listed, but the person's head stays on top."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=4)
    run_action(db, "register_model", {"model": cloud_model()})
    with use_transport(httpx.MockTransport(EditingVision(db, tasks))):
        run = PrelabelRun.model_validate(run_action(db, "run_prelabel", _values(project.id)).root)
    assert run.revision_ids == ()
    assert {failure.code for failure in run.failures} == {"task_changed"}
    assert len(run.failures) == 4
    assert run.cost > 0
    for task in tasks:
        assert list_revisions(db, task.id)[-1].source == "human"


def test_stale_limit_is_long_enough_for_a_slow_batch() -> None:
    """A batch of four slow images reports progress well within the takeover limit."""
    assert timedelta(minutes=5) < STALE_AFTER
