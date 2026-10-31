# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact human workload, model confidence buckets and reused annotation quality measurements."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ReviewTaskParams,
    SaveRevisionParams,
    SubmitTaskParams,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import new_id
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
