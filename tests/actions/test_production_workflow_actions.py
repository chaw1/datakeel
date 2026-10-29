# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real controlled-action chains retain approvals, idempotency, optimistic locking and audit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.approvals import approve_plan
from datakeel.actions.execution import execute_plan
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.planning import prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.production_models import AnnotationRevision, ProductionTask, Project
from datakeel.storage.action_rows import ActionAuditRow
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    list_assignments,
    list_reviews,
    list_tasks,
    project_progress,
)
from datakeel.storage.production_revisions import RevisionConflictError
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from collections.abc import Mapping

    from datakeel.actions.models import ActionPlan, ActionRun
    from datakeel.storage.database import Database


def _prepare(
    db: Database, action: str, values: Mapping[str, object], actor: str = "local"
) -> ActionPlan:
    return prepare_action(
        db,
        action,
        JsonDocument.model_validate({"request_id": new_id(), **values}),
        ActionContext(actor=actor),
    )


def _run(
    db: Database, action: str, values: Mapping[str, object], actor: str = "local"
) -> ActionRun:
    plan = _prepare(db, action, values, actor)
    if plan.requires_approval:
        approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor)
        )
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor))


def _details(run: ActionRun) -> JsonDocument:
    assert run.status == "SUCCEEDED"
    assert run.receipt is not None
    return JsonDocument.model_validate(run.receipt.quality["details"])


def _save(db: Database, task: ProductionTask, actor: str = "local") -> AnnotationRevision:
    values = {
        "task_id": task.id,
        "previous_revision_id": task.latest_revision_id,
        "annotation": {"sample_id": task.sample_id, "annotator_id": actor, "labels": ["cat"]},
    }
    return AnnotationRevision.model_validate(
        _details(_run(db, "save_revision", values, actor)).root, extra="ignore"
    )


def test_personal_action_chain_is_audited_and_has_no_assignment_or_human_review(
    db: Database,
) -> None:
    """Public planning saves, auto-approves, reopens and upgrades without fake reviewers."""
    project, tasks = production_fixture(db)
    revision = _save(db, tasks[0])
    submitted = _run(db, "submit_task", {"task_id": tasks[0].id})
    assert ProductionTask.model_validate(_details(submitted).root).state == "approved"
    with db.session() as session:
        audits = list(
            session.scalars(
                select(ActionAuditRow).where(
                    ActionAuditRow.plan_id == submitted.plan_id,
                    ActionAuditRow.phase == "SYSTEM_APPROVAL",
                )
            )
        )
    assert len(audits) == 1
    assert audits[0].status == "APPROVED"
    assert list_assignments(db, tasks[0].id) == ()
    assert list_reviews(db, tasks[0].id) == ()
    _run(db, "reopen_task", {"task_id": tasks[0].id, "reason": "Correction"})
    assert get_task(db, tasks[0].id).latest_revision_id == revision.id
    for tier in ("group", "team"):
        _run(db, "upgrade_project", {"project_id": project.id, "workflow_tier": tier})
    assert get_project(db, project.id).workflow_tier == "team"


def test_create_project_requires_approval_then_split_records_precise_partitions(
    db: Database,
) -> None:
    """Project creation is signed; partitioning is audited against the immutable version."""
    seed, _ = production_fixture(db)
    plan = _prepare(
        db,
        "create_project",
        {
            "name": "Second project",
            "dataset_id": seed.dataset_id,
            "version_id": seed.version_id,
            "label_set_id": seed.label_set_id,
        },
    )
    assert plan.requires_approval
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    created = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    project = Project.model_validate(_details(created).root)
    assert project.workflow_tier == "personal"
    result = _run(db, "split_packages", {"project_id": project.id, "package_size": 2})
    packages = _details(result).root["packages"]
    assert isinstance(packages, list)
    assert len(packages) == 2
    assert len(list_tasks(db, project.id)) == 3
    assert project_progress(db, project.id).total == 3


def test_group_action_chain_assigns_claims_reviews_and_returns_rework_to_same_actor(
    db: Database,
) -> None:
    """Group self review retains each rejected revision and assignment in history."""
    project, tasks = production_fixture(db, "group")
    assigned = _run(db, "assign_tasks", {"task_ids": [tasks[0].id], "actor": "a"})
    assert _details(assigned).root["suggest_review"] is True
    first = _save(db, get_task(db, tasks[0].id), "a")
    _run(db, "submit_task", {"task_id": tasks[0].id}, "a")
    _run(
        db,
        "review_task",
        {
            "task_id": tasks[0].id,
            "revision_id": first.id,
            "decision": "rework",
            "issues": ["Fix boundary"],
        },
        "a",
    )
    assert get_task(db, tasks[0].id).round == 1
    second = _save(db, get_task(db, tasks[0].id), "a")
    _run(db, "submit_task", {"task_id": tasks[0].id}, "a")
    _run(
        db,
        "review_task",
        {"task_id": tasks[0].id, "revision_id": second.id, "decision": "approve"},
        "a",
    )
    assert get_task(db, tasks[0].id).approved_revision_id == second.id
    claimed = _run(db, "claim_task", {"project_id": project.id}, "b")
    claimed_task = ProductionTask.model_validate(_details(claimed).root, extra="ignore")
    assert _details(claimed).root["suggest_review"] is False
    _run(db, "release_task", {"task_id": claimed_task.id}, "b")
    assert get_task(db, claimed_task.id).state == "pending"


def test_production_request_replay_reuses_original_run_and_rejects_changed_inputs(
    db: Database,
) -> None:
    """Client retries reuse one plan, revision and receipt after the task changes."""
    _, tasks = production_fixture(db)
    values = {
        "request_id": "same-client-request",
        "task_id": tasks[0].id,
        "previous_revision_id": None,
        "annotation": {"sample_id": tasks[0].sample_id, "annotator_id": "local", "labels": ["cat"]},
    }
    first = _run(db, "save_revision", values)
    second = _run(db, "save_revision", values)
    assert second == first
    with pytest.raises(ConflictError, match="different"):
        _prepare(db, "save_revision", {**values, "previous_revision_id": "forged"})


def test_stale_prepared_revision_plan_returns_current_server_head(db: Database) -> None:
    """Concurrent prepared saves are protected by previous-revision CAS at actual execution time."""
    _, tasks = production_fixture(db)
    first = _save(db, tasks[0])
    values = {
        "task_id": tasks[0].id,
        "previous_revision_id": first.id,
        "annotation": {"sample_id": tasks[0].sample_id, "annotator_id": "local", "labels": ["cat"]},
    }
    stale = _prepare(db, "save_revision", values)
    latest = _save(db, get_task(db, tasks[0].id))
    with pytest.raises(RevisionConflictError) as rejected:
        execute_plan(db, stale.id, ExecuteRequest(plan_digest=stale.plan_digest))
    assert rejected.value.latest_revision == latest


def test_public_save_cannot_forge_model_source_to_bypass_assignment(db: Database) -> None:
    """Only the controlled prediction import can write model provenance."""
    _, tasks = production_fixture(db, "group")
    with pytest.raises(ValidationError, match="Model revisions"):
        _run(
            db,
            "save_revision",
            {
                "task_id": tasks[0].id,
                "previous_revision_id": None,
                "source": "model",
                "model_name": "forged",
                "model_version": "1",
                "annotation": {
                    "sample_id": tasks[0].sample_id,
                    "annotator_id": "forged",
                    "labels": ["cat"],
                },
            },
        )


def test_reviewer_claim_capability_does_not_grant_annotation_writes(db: Database) -> None:
    """A reviewer can claim review work while annotation claiming and saving remain denied."""
    project, tasks = production_fixture(db, "group")
    _run(db, "manage_users", {"operation": "create", "user_id": "local"})
    _run(db, "manage_users", {"operation": "create", "user_id": "a", "role_ids": ["annotator"]})
    _run(db, "manage_users", {"operation": "create", "user_id": "q", "role_ids": ["reviewer"]})
    with pytest.raises(AuthorizationError, match="stage scope"):
        _run(db, "claim_task", {"project_id": project.id}, "q")
    with pytest.raises(AuthorizationError):
        _save(db, tasks[0], "q")
    _run(db, "assign_tasks", {"task_ids": [tasks[0].id], "actor": "a"})
    revision = _save(db, get_task(db, tasks[0].id), "a")
    _run(db, "submit_task", {"task_id": tasks[0].id}, "a")
    claimed = _run(db, "claim_task", {"project_id": project.id, "stage": "review"}, "q")
    assert ProductionTask.model_validate(_details(claimed).root, extra="ignore").id == tasks[0].id
    _run(
        db,
        "review_task",
        {"task_id": tasks[0].id, "revision_id": revision.id, "decision": "approve"},
        "q",
    )
    assert get_task(db, tasks[0].id).state == "approved"
