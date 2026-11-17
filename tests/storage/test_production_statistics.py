# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact human workload, model confidence buckets and reused annotation quality measurements."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ReviewTaskParams,
    SaveRevisionParams,
    SubmitTaskParams,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import new_id
from datakeel.core.production_reads import ReworkRateParams
from datakeel.ontology.production_functions import rework_rate_workload
from datakeel.storage import production_reviews
from datakeel.storage.production_assignments import assign_tasks
from datakeel.storage.production_reviews import review_task, submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_statistics import (
    annotator_workload,
    confidence_distribution,
    production_agreement,
)
from datakeel.storage.production_tasks import require_task
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_confidence_distribution_counts_all_model_revisions_at_bucket_boundaries(
    db: Database,
) -> None:
    """Confidence zero and one belong to the edge buckets; human revisions do not inflate totals."""
    project, tasks = production_fixture(db)
    confidences = (0.0, 0.1, 0.99, 1.0)
    with db.session() as session:
        previous = None
        for confidence in confidences:
            revision = append_revision(
                session,
                require_task(session, tasks[0].id),
                SaveRevisionParams(
                    request_id=new_id(),
                    task_id=tasks[0].id,
                    previous_revision_id=previous,
                    annotation=AnnotationRecord(
                        sample_id=tasks[0].sample_id, annotator_id="fake-model", labels=("cat",)
                    ),
                    source="model",
                    model_name="Fixture",
                    model_version="1",
                    confidence=confidence,
                ),
                "local",
            )
            previous = revision.id
        append_revision(
            session,
            require_task(session, tasks[0].id),
            SaveRevisionParams(
                request_id=new_id(),
                task_id=tasks[0].id,
                previous_revision_id=previous,
                annotation=AnnotationRecord(
                    sample_id=tasks[0].sample_id, annotator_id="human", labels=("cat",)
                ),
            ),
            "local",
        )
        session.commit()
    distribution = confidence_distribution(db, project.id)
    assert distribution.total == 4
    assert tuple(bucket.count for bucket in distribution.buckets) == (1, 1, 0, 0, 0, 0, 0, 0, 0, 2)
    agreement = production_agreement(db, project.id)
    assert (agreement.sample_count, agreement.annotator_count) == (1, 2)


def test_workload_reports_distinct_tasks_review_decisions_and_rework_rate(db: Database) -> None:
    """One task reviewed twice has one completion and a fifty-percent rework rate."""
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        assign_tasks(
            session, AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="a")
        )
        session.commit()
    previous = None
    for decision in ("rework", "approve"):
        with db.session() as session:
            revision = append_revision(
                session,
                require_task(session, tasks[0].id),
                SaveRevisionParams(
                    request_id=new_id(),
                    task_id=tasks[0].id,
                    previous_revision_id=previous,
                    annotation=AnnotationRecord(
                        sample_id=tasks[0].sample_id, annotator_id="a", labels=("cat",)
                    ),
                ),
                "a",
            )
            submit_task(session, SubmitTaskParams(request_id=new_id(), task_id=tasks[0].id), "a")
            review_task(
                session,
                ReviewTaskParams(
                    request_id=new_id(),
                    task_id=tasks[0].id,
                    revision_id=revision.id,
                    decision=decision,
                    issues=("Correct label",) if decision == "rework" else (),
                ),
                "q",
            )
            session.commit()
            previous = revision.id
    workload = annotator_workload(db, project.id).annotators[0]
    assert (workload.actor, workload.assigned, workload.completed) == ("a", 1, 1)
    assert (workload.rework_count, workload.review_count) == (1, 2)
    assert workload.rework_rate == pytest.approx(0.5)


def test_empty_project_statistics_have_no_invented_observations(db: Database) -> None:
    """A project with no saved annotations returns explicit empty quality and workload values."""
    project, _ = production_fixture(db)
    assert annotator_workload(db, project.id).annotators == ()
    assert confidence_distribution(db, project.id).total == 0
    assert production_agreement(db, project.id).sample_count == 0


def test_model_only_personal_submission_counts_the_human_submitter(db: Database) -> None:
    """Confirming unchanged model predictions records the human submitter's completed task.

    A model head cannot be submitted as it is; the submitter saves it unchanged as their own.
    """
    project, tasks = production_fixture(db, count=1)
    with db.session() as session:
        draft = append_revision(
            session,
            require_task(session, tasks[0].id),
            SaveRevisionParams(
                request_id="model",
                task_id=tasks[0].id,
                previous_revision_id=None,
                annotation=AnnotationRecord(
                    sample_id=tasks[0].sample_id, annotator_id="fake-model", labels=("cat",)
                ),
                source="model",
                model_name="Fixture",
                model_version="1",
                confidence=0.8,
            ),
            "submitter",
        )
        revision = append_revision(
            session,
            require_task(session, tasks[0].id),
            SaveRevisionParams(
                request_id="confirm",
                task_id=tasks[0].id,
                previous_revision_id=draft.id,
                annotation=draft.annotation.model_copy(update={"annotator_id": "submitter"}),
            ),
            "submitter",
        )
        task = submit_task(
            session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "submitter"
        )
        session.commit()
    assert task.approved_revision_id == revision.id
    workload = annotator_workload(db, project.id).annotators[0]
    assert (workload.actor, workload.completed) == ("submitter", 1)


def _seed_timed_reviews(db: Database, monkeypatch: pytest.MonkeyPatch) -> str:
    project, tasks = production_fixture(db, "group", count=3)
    stamps = (
        (tasks[0], "rework", datetime(2026, 10, 25, 10, 0, tzinfo=UTC)),
        (tasks[1], "rework", datetime(2026, 11, 12, 10, 0, tzinfo=UTC)),
        (tasks[2], "approve", datetime(2026, 11, 18, 9, 0, tzinfo=UTC)),
    )
    with db.session() as session:
        assign_tasks(
            session,
            AssignTasksParams(
                request_id="assign-all",
                task_ids=tuple(task.id for task in tasks),
                actor="a",
            ),
        )
        session.commit()
    for task, decision, stamp in stamps:
        monkeypatch.setattr(production_reviews, "utcnow", lambda at=stamp: at)
        with db.session() as session:
            rev = append_revision(
                session,
                require_task(session, task.id),
                SaveRevisionParams(
                    request_id=new_id(),
                    task_id=task.id,
                    previous_revision_id=None,
                    annotation=AnnotationRecord(
                        sample_id=task.sample_id, annotator_id="a", labels=("cat",)
                    ),
                ),
                "a",
            )
            submit_task(session, SubmitTaskParams(request_id=new_id(), task_id=task.id), "a")
            review_task(
                session,
                ReviewTaskParams(
                    request_id=new_id(),
                    task_id=task.id,
                    revision_id=rev.id,
                    decision="rework" if decision == "rework" else "approve",
                    issues=("Fix",) if decision == "rework" else (),
                ),
                "q",
            )
            session.commit()
    return project.id


def test_rework_rate_workload_filters_by_named_windows_days_and_explicit_bounds(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UTC review windows isolate today, this/last week, month, rolling days, and bounds."""
    project_id = _seed_timed_reviews(db, monkeypatch)
    now = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)

    def _stats(params: ReworkRateParams) -> tuple[int, int, float]:
        row = rework_rate_workload(db, params, now=now).annotators[0]
        return row.rework_count, row.review_count, row.rework_rate

    assert _stats(ReworkRateParams(project_id=project_id)) == (2, 3, pytest.approx(2 / 3))
    assert _stats(ReworkRateParams(project_id=project_id, window="all_time")) == (
        2,
        3,
        pytest.approx(2 / 3),
    )
    assert _stats(ReworkRateParams(project_id=project_id, window="today")) == (0, 1, 0.0)
    assert _stats(ReworkRateParams(project_id=project_id, window="this_week")) == (0, 1, 0.0)
    assert _stats(ReworkRateParams(project_id=project_id, window="last_week")) == (1, 1, 1.0)
    assert _stats(ReworkRateParams(project_id=project_id, window="this_month")) == (1, 2, 0.5)
    assert _stats(ReworkRateParams(project_id=project_id, window="last_7_days")) == (1, 2, 0.5)
    assert _stats(ReworkRateParams(project_id=project_id, window="last_30_days")) == (
        2,
        3,
        pytest.approx(2 / 3),
    )
    assert _stats(ReworkRateParams(project_id=project_id, days=2)) == (0, 1, 0.0)
    assert _stats(
        ReworkRateParams(
            project_id=project_id,
            since=datetime(2026, 11, 10, 0, 0, tzinfo=UTC),
            until=datetime(2026, 11, 15, 0, 0, tzinfo=UTC),
        )
    ) == (1, 1, 1.0)
    with pytest.raises(ValidationError):
        ReworkRateParams(project_id=project_id, since=now, until=now - timedelta(days=1))
