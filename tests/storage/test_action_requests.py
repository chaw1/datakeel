# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Operation replay is durable, parameter-bound, and independent of target mutation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.models import ActionPlan, ApprovalDecision, ExecuteRequest
from datakeel.actions.policy import digest, plan_digest
from datakeel.actions.service import approve_plan, execute_plan, list_runs, prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.core.models import JsonDocument, utcnow
from datakeel.storage.action_rows import ActionAuditRow, ActionOperationRow, ActionPlanRow
from datakeel.storage.database import EventRow
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.fixture
def plan(db: Database, tmp_path: Path) -> ActionPlan:
    """Prepare one locally generated immutable selection with a server operation ID."""
    path = tmp_path / "replay.txt"
    path.write_text("A synthetic operation replay fixture.")
    dataset = import_paths(db, "replay", [path])
    return prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset.id}})
    )


def request_for(plan: ActionPlan) -> ExecuteRequest:
    """Use the replay identity supplied by prepare rather than a client-generated ID."""
    assert plan.operation_id
    return ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)


def test_replay_when_target_changed_returns_original_receipt_without_new_writes(
    db: Database, plan: ActionPlan, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A committed result remains replayable after target state and plan expiry change."""
    request = request_for(plan)
    original = execute_plan(db, plan.id, request)
    monkeypatch.setattr("datakeel.actions.policy.utcnow", lambda: utcnow() + timedelta(days=1))
    assert execute_plan(db, plan.id, request) == original
    assert len(list_runs(db)) == 1
    with db.session() as session:
        assert len(list(session.scalars(select(ActionOperationRow)))) == 1
        assert len(list(session.scalars(select(ActionAuditRow)))) == 2
        assert len(list(session.scalars(select(EventRow)))) == 2


def test_replay_when_canonical_params_supplied_accepts_same_effective_request(
    db: Database, plan: ActionPlan
) -> None:
    """Omitted and explicitly identical canonical parameters name the same operation."""
    request = request_for(plan)
    original = execute_plan(db, plan.id, request)
    retry = request.model_copy(update={"canonical_params": plan.canonical_params})
    assert execute_plan(db, plan.id, retry) == original


@pytest.mark.parametrize("execute_first", [False, True])
def test_execute_when_digest_wrong_does_not_record_run_before_or_after_consumption(
    db: Database, plan: ActionPlan, *, execute_first: bool
) -> None:
    """A wrong digest remains a plain conflict even when a matching operation exists."""
    request = request_for(plan)
    if execute_first:
        execute_plan(db, plan.id, request)
    before = list_runs(db)
    with pytest.raises(ConflictError, match="plan_digest"):
        execute_plan(db, plan.id, request.model_copy(update={"plan_digest": "wrong"}))
    assert list_runs(db) == before


@pytest.mark.parametrize("execute_first", [False, True])
def test_execute_when_actor_wrong_never_returns_receipt_or_records_denied_run(
    db: Database, plan: ActionPlan, *, execute_first: bool
) -> None:
    """An unauthorized caller cannot discover a previously committed operation result."""
    request = request_for(plan)
    if execute_first:
        execute_plan(db, plan.id, request)
    before = list_runs(db)
    with pytest.raises(AuthorizationError, match="actor"):
        execute_plan(db, plan.id, request.model_copy(update={"actor": "another"}))
    assert list_runs(db) == before


def test_replay_when_canonical_params_change_does_not_reuse_receipt(
    db: Database, plan: ActionPlan
) -> None:
    """The operation identity cannot conceal a changed execution request."""
    request = request_for(plan)
    original = execute_plan(db, plan.id, request)
    with pytest.raises(ConflictError, match="Canonical parameters"):
        execute_plan(db, plan.id, request.model_copy(update={"canonical_params": {}}))
    assert list_runs(db) == [original]


def test_execute_when_operation_belongs_to_another_plan_is_rejected_without_run(
    db: Database, plan: ActionPlan
) -> None:
    """A valid digest and actor cannot substitute a different server-issued operation ID."""
    other = prepare_action(db, "unquarantine_files", JsonDocument(plan.canonical_params))
    with pytest.raises(ConflictError, match="Operation identity"):
        execute_plan(
            db,
            other.id,
            ExecuteRequest(plan_digest=other.plan_digest, operation_id=plan.operation_id),
        )
    assert list_runs(db) == []


def test_execute_when_legacy_request_repeats_consumed_plan_records_denied(
    db: Database, plan: ActionPlan
) -> None:
    """Only a matching explicit operation identity permits replay of a consumed plan."""
    execute_plan(db, plan.id, request_for(plan))
    with pytest.raises(ConflictError):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_runs(db)[0].status == "DENIED"
    assert list_runs(db)[0].reason == (
        "ConflictError: Action plan was already executed; approval was consumed"
    )


def test_replay_when_initial_request_denied_returns_same_denial_audit(
    db: Database, plan: ActionPlan
) -> None:
    """A rejected plan keeps its status and creates only one denied run per operation."""
    deletion = prepare_action(db, "delete_files", JsonDocument(plan.canonical_params))
    approve_plan(db, deletion.id, ApprovalDecision(approve=False, plan_digest=deletion.plan_digest))
    request = request_for(deletion)
    with pytest.raises(ConflictError, match="rejected"):
        execute_plan(db, deletion.id, request)
    denied = list_runs(db)[0]
    assert denied.status == "DENIED"
    assert execute_plan(db, deletion.id, request) == denied
    assert len(list_runs(db)) == 1
    assert len(list_files(db, plan.manifest.query.dataset_id or "")) == 1


def test_replay_when_worker_completes_returns_same_run_with_final_receipt(
    db: Database, plan: ActionPlan
) -> None:
    """Queued operation retries do not enqueue another task or rerun completed work."""
    pipeline = prepare_action(
        db, "run_pipeline", JsonDocument({"dataset_id": plan.manifest.query.dataset_id})
    )
    request = request_for(pipeline)
    queued = execute_plan(db, pipeline.id, request)
    assert queued.status == "QUEUED"
    assert execute_plan(db, pipeline.id, request) == queued
    run_worker(db, once=True)
    completed = execute_plan(db, pipeline.id, request)
    assert completed.id == queued.id
    assert completed.status == "SUCCEEDED"
    assert completed.receipt is not None
    assert len(list_runs(db)) == 1


def test_replay_when_requests_concurrent_returns_one_run(db: Database, plan: ActionPlan) -> None:
    """Concurrent retries serialize and share one durable business outcome."""
    request = request_for(plan)

    def execute_once(_index: int) -> str:
        return execute_plan(db, plan.id, request).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(pool.map(execute_once, range(2)))
    assert identifiers[0] == identifiers[1]
    assert len(list_runs(db)) == 1


def test_execute_when_plan_predates_operation_field_preserves_frozen_digest(
    db: Database, plan: ActionPlan
) -> None:
    """Loading an older stored plan must not silently change its approval digest."""
    payload = plan.model_dump(mode="json", exclude={"operation_id"})
    payload["plan_digest"] = digest(
        {key: value for key, value in payload.items() if key not in {"plan_digest", "status"}}
    )
    legacy = ActionPlan.model_validate(payload)
    assert legacy.operation_id is None
    assert plan_digest(legacy) == legacy.plan_digest
    with db.session() as session:
        row = session.get(ActionPlanRow, plan.id)
        assert row is not None
        row.payload = payload
        session.commit()
    assert execute_plan(db, plan.id, ExecuteRequest(plan_digest=legacy.plan_digest)).status == (
        "SUCCEEDED"
    )
