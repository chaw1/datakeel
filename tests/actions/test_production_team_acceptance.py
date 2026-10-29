# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team package acceptance reuses P26 sampling, returns whole packages and gates finalization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision
from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord
from datakeel.core.annotation_sampling import AnnotationImportRequest, SamplingRequest
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.production_team_models import PackageInspection
from datakeel.storage.annotation_sampling import create_sampling_plan
from datakeel.storage.annotation_store import import_annotations
from datakeel.storage.production_queries import get_task, list_packages, list_tasks
from tests.production_helpers import production_fixture
from tests.production_team_ops import (
    approve_all,
    claim,
    failure,
    review,
    save,
    submit,
    team_project,
)
from tests.production_team_support import ServiceRunner, accept_package, acceptance

if TYPE_CHECKING:
    from datakeel.core.models import JsonDocument
    from datakeel.core.production_models import ProductionTask, Project
    from datakeel.storage.database import Database

RATIO = {"method": "ratio", "ratio": 0.5, "acceptance_number": 1, "seed": 7}


def _approved_team(
    db: Database, count: int = 20, package_size: int = 100
) -> tuple[Project, tuple[ProductionTask, ...], str]:
    project, tasks = team_project(db, count=count, package_size=package_size)
    approve_all(db, project.id, tasks)
    return project, tasks, list_packages(db, project.id)[0].id


def _inspect(
    runner: ServiceRunner, db: Database, project: Project, package_id: str, defects: int
) -> PackageInspection:
    preview = acceptance(db, project.id, package_id, **RATIO)
    assert preview.sampling is not None
    flagged = set(preview.sampling.sample_ids[:defects])
    checks = [
        {"sample_id": sample, "defective": True, "reason": "Generated defect"}
        if sample in flagged
        else {"sample_id": sample, "defective": False}
        for sample in preview.sampling.sample_ids
    ]
    details = runner("accept_package", {"package_id": package_id, "checks": checks, **RATIO})
    return PackageInspection.model_validate(details.root)


def _rework_all(db: Database, project: Project) -> None:
    for task in list_tasks(db, project.id):
        claimed = claim(db, project.id, "annotator-a")
        assert claimed.round == task.round == 1
        save(db, claimed.id, "annotator-a")
        submit(db, claimed.id, "annotator-a")
    for _ in list_tasks(db, project.id):
        claimed = claim(db, project.id, "reviewer-b", "review")
        review(db, claimed.id, "reviewer-b")


@pytest.mark.parametrize("sampling", [{}, RATIO, {"aql": 1.0, "seed": 3}])
def test_package_sample_equals_the_p26_plan_for_the_same_units(
    db: Database, sampling: dict[str, object]
) -> None:
    """Imported as a P26 batch, the same units give the same lot, sample and decision numbers."""
    project, tasks, package_id = _approved_team(db)
    preview = acceptance(db, project.id, package_id, **sampling)
    assert preview.status == "ready"
    assert preview.sampling is not None
    batch = AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(sample_id=task.sample_id, annotator_id="annotator-a", labels=("cat",))
            for task in tasks
        )
    )
    report = import_annotations(
        db,
        project.dataset_id,
        AnnotationImportRequest(version_id=project.version_id, batch=batch, idempotency_key="p26"),
    )
    plan = create_sampling_plan(
        db, project.dataset_id, SamplingRequest(batch_id=report.id, **sampling)
    )
    ours = preview.sampling
    assert (ours.lot_size, ours.sample_size, ours.sample_ids) == (
        plan.lot_size,
        plan.sample_size,
        plan.sample_ids,
    )
    assert (ours.acceptance_number, ours.rejection_number) == (
        plan.acceptance_number,
        plan.rejection_number,
    )
    assert (ours.code_letter, ours.effective_code_letter) == (
        plan.code_letter,
        plan.effective_code_letter,
    )
    by_sample = {task.sample_id: task.id for task in tasks}
    assert ours.task_ids == tuple(sorted(by_sample[sample] for sample in ours.sample_ids))


def test_acceptance_is_a_human_decision_and_unlocks_finalization(db: Database) -> None:
    """Models may prepare the plan only; a person approves, and then the project finalizes."""
    project, _tasks, package_id = _approved_team(db, count=4)
    runner = ServiceRunner(db)
    blocked = failure(lambda: runner("finalize_project", {"project_id": project.id}))
    assert isinstance(blocked, ConflictError), blocked
    assert package_id in str(blocked)
    preview = acceptance(db, project.id, package_id)
    assert preview.sampling is not None
    checks = [{"sample_id": sample, "defective": False} for sample in preview.sampling.sample_ids]
    plan = runner.plan("accept_package", {"package_id": package_id, "checks": checks})
    assert plan.requires_approval
    decision = ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor="local")
    model = AccessContext(actor="local", entry="mcp", scope="query")
    refused = failure(lambda: service.approve_plan(db, plan.id, decision, access=model))
    assert isinstance(refused, AuthorizationError), refused
    accept_package(db, runner, project.id, package_id)
    assert acceptance(db, project.id, package_id).status == "accepted"
    version = runner("finalize_project", {"project_id": project.id})
    assert version.root["produced_by_project"] == project.id


def test_rejection_returns_every_package_task_for_one_more_round(db: Database) -> None:
    """Defects above the acceptance number send all tasks back, sampled or not."""
    project, tasks, package_id = _approved_team(db)
    runner = ServiceRunner(db)
    inspection = _inspect(runner, db, project, package_id, defects=2)
    assert (inspection.accepted, inspection.defective_count) == (False, 2)
    assert inspection.sampling.sample_size == 10
    assert set(inspection.returned_task_ids) == {task.id for task in tasks}
    for task in tasks:
        current = get_task(db, task.id)
        assert (current.state, current.round, current.approved_revision_id) == ("pending", 1, None)
        assert current.annotator_id == "annotator-a"
    assert acceptance(db, project.id, package_id).status == "rejected"
    error = failure(lambda: runner("finalize_project", {"project_id": project.id}))
    assert isinstance(error, ConflictError), error
    _rework_all(db, project)
    assert acceptance(db, project.id, package_id, **RATIO).status == "ready"
    second = _inspect(runner, db, project, package_id, defects=1)
    assert (second.accepted, second.returned_task_ids) == (True, ())
    assert all(get_task(db, task.id).round == 1 for task in tasks)
    runner("finalize_project", {"project_id": project.id})


def test_acceptance_requires_full_approval_exact_checks_and_team_tier(db: Database) -> None:
    """Incomplete packages, partial inspections and group projects are refused explicitly."""
    project, tasks = team_project(db, count=3)
    runner = ServiceRunner(db)
    package_id = list_packages(db, project.id)[0].id
    unready = failure(
        lambda: runner(
            "accept_package",
            {
                "package_id": package_id,
                "checks": [{"sample_id": tasks[0].sample_id, "defective": False}],
            },
        )
    )
    assert isinstance(unready, ConflictError), unready
    approve_all(db, project.id, tasks)
    preview = acceptance(db, project.id, package_id)
    assert preview.sampling is not None
    assert preview.sampling.sample_size > 1
    partial = [{"sample_id": preview.sampling.sample_ids[0], "defective": False}]
    short = failure(lambda: runner("accept_package", {"package_id": package_id, "checks": partial}))
    assert isinstance(short, ValidationError), short
    assert "every sampled unit" in str(short)
    outsider = [*partial, {"sample_id": "not-in-package", "defective": False}]
    extra = failure(
        lambda: runner("accept_package", {"package_id": package_id, "checks": outsider})
    )
    assert isinstance(extra, ValidationError), extra
    group, group_tasks = production_fixture(db, "group", count=2)
    group_package = list_packages(db, group.id)[0].id
    rejected = failure(
        lambda: runner(
            "accept_package",
            {
                "package_id": group_package,
                "checks": [{"sample_id": group_tasks[0].sample_id, "defective": False}],
            },
        )
    )
    assert isinstance(rejected, ValidationError), rejected


def test_reopening_after_acceptance_requires_a_new_acceptance(db: Database) -> None:
    """An acceptance covers the exact approved revisions; changing one invalidates it."""
    project, tasks, package_id = _approved_team(db, count=4)
    runner = ServiceRunner(db)
    accept_package(db, runner, project.id, package_id)
    runner("reopen_task", {"task_id": tasks[0].id, "reason": "Generated recheck"})
    assert acceptance(db, project.id, package_id).status == "in_progress"
    claimed = claim(db, project.id, "annotator-a")
    save(db, claimed.id, "annotator-a")
    submit(db, claimed.id, "annotator-a")
    claim(db, project.id, "reviewer-b", "review")
    review(db, claimed.id, "reviewer-b")
    assert acceptance(db, project.id, package_id).status == "ready"
    error = failure(lambda: runner("finalize_project", {"project_id": project.id}))
    assert isinstance(error, ConflictError), error
    accept_package(db, runner, project.id, package_id)
    runner("finalize_project", {"project_id": project.id})


def test_finalization_waits_for_every_package(db: Database) -> None:
    """With two packages, accepting one is not enough to finalize the project."""
    project, _tasks, _package = _approved_team(db, count=6, package_size=3)
    runner = ServiceRunner(db)
    first, second = (package.id for package in list_packages(db, project.id))
    accept_package(db, runner, project.id, first)
    error = failure(lambda: runner("finalize_project", {"project_id": project.id}))
    assert isinstance(error, ConflictError), error
    assert second in str(error)
    assert first not in str(error)
    accept_package(db, runner, project.id, second)
    details: JsonDocument = runner("finalize_project", {"project_id": project.id})
    assert details.root["produced_by_project"] == project.id
