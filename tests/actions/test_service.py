# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify approval, canonicalization, authorization, and durable receipt invariants."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.models import (
    ActionContext,
    ActionPlan,
    ActionRun,
    ApprovalDecision,
    ExecuteRequest,
)
from datakeel.actions.service import (
    approve_plan,
    execute_plan,
    list_approvals,
    list_runs,
    prepare_action,
)
from datakeel.core.errors import AuthorizationError, BudgetError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument, utcnow
from datakeel.storage.action_rows import ActionAuditRow, ActionPlanRow, ApprovalRow
from datakeel.storage.database import Database, EventRow, OutboxRow
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.file_state import get_file_state

if TYPE_CHECKING:
    from pathlib import Path

    from tests.actions.conftest import DatasetFixture


def prepare(
    db: Database,
    dataset_id: str,
    action: str = "quarantine_files",
    *,
    context: ActionContext | None = None,
) -> ActionPlan:
    """Provide the prepare test fixture."""
    return prepare_action(
        db, action, JsonDocument({"selection": {"dataset_id": dataset_id}}), context=context
    )


def approve(db: Database, plan: ActionPlan) -> ActionPlan:
    """Provide the approve test fixture."""
    return approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))


def execute(db: Database, plan: ActionPlan) -> ActionRun:
    """Provide the execute test fixture."""
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_reversible_mutation_has_attributed_atomic_receipt_and_outbox(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify reversible mutation has attributed atomic receipt and outbox."""
    created, files = dataset
    plan = prepare(db, created.id, context=ActionContext(agent_id="fixture", session_id="session"))
    assert plan.impact.object_count == 3
    assert not plan.requires_approval
    assert list_approvals(db) == []
    run = execute(db, plan)
    assert run.status == "SUCCEEDED"
    assert run.receipt.on_behalf_of == "agent:fixture/session:session"
    assert any(
        ref.asset_type == "action_run" and ref.asset_id == run.id for ref in run.receipt.outputs
    )
    assert any(
        ref.asset_type == "dataset" and ref.asset_id == created.id for ref in run.receipt.inputs
    )
    with db.session() as session:
        assert all(get_file_state(session, created.id, file.id).quarantined for file in files)
        assert session.scalar(select(EventRow).where(EventRow.event_id == run.receipt.event_id))
        assert session.scalar(
            select(OutboxRow).where(OutboxRow.idempotency_key == run.receipt.idempotency_key)
        )
        assert len(list(session.scalars(select(ActionAuditRow)))) == 2
    inverse = prepare(db, created.id, "unquarantine_files")
    execute(db, inverse)
    assert all(not file.metadata["quarantined"] for file in list_files(db, created.id))


def test_irreversible_action_waits_for_single_use_approval(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify irreversible action waits for single use approval."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files")
    assert [value.id for value in list_approvals(db)] == [plan.id]
    with pytest.raises(AuthorizationError, match="human approval"):
        execute(db, plan)
    failure = list_runs(db)[0]
    assert failure.status == "DENIED"
    assert failure.reason == "AuthorizationError: Action requires explicit human approval"
    assert failure.receipt.run_state == "FAIL"
    assert failure.receipt.outputs == []
    approve(db, plan)
    run = execute(db, plan)
    assert run.status == "SUCCEEDED"
    assert list_files(db, created.id) == []
    with pytest.raises(ConflictError, match=r"changed|executed|consumed"):
        execute(db, plan)
    with db.session() as session:
        assert session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id)).consumed


def test_rejected_approval_never_executes(db: Database, dataset: DatasetFixture) -> None:
    """Verify rejected approval never executes."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files")
    rejected = approve_plan(
        db,
        plan.id,
        ApprovalDecision(approve=False, plan_digest=plan.plan_digest, reason="Keep fixture"),
    )
    assert rejected.status == "REJECTED"
    with pytest.raises(ConflictError, match="rejected"):
        execute(db, plan)
    denied = list_runs(db)[0]
    assert denied.status == "DENIED"
    assert denied.reason == "ConflictError: Human approval was rejected"
    assert denied.receipt is not None
    assert denied.receipt.run_state == "FAIL"
    assert denied.receipt.outputs == []
    with db.session() as session:
        audit = session.scalars(
            select(ActionAuditRow).where(ActionAuditRow.phase == "EXECUTE")
        ).one()
        assert audit.status == "DENIED"
    assert len(list_files(db, created.id)) == 3
    with pytest.raises(ConflictError, match="decision"):
        approve(db, plan)


def test_changed_canonical_params_cannot_reuse_approval(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify changed canonical params cannot reuse approval."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files")
    approve(db, plan)
    with pytest.raises(ConflictError, match="Canonical parameters"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, canonical_params={}))
    assert len(list_files(db, created.id)) == 3


@pytest.mark.parametrize(
    ("alteration", "reason"),
    [
        ("consumed", "Human approval was already consumed"),
        ("digest", "Human approval no longer matches the plan"),
    ],
)
def test_approval_when_consumed_or_unbound_is_denied_before_business_execution(
    db: Database, dataset: DatasetFixture, alteration: str, reason: str
) -> None:
    """An invalid stored approval never authorizes mutation despite an approved plan."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files")
    approve(db, plan)
    with db.session() as session:
        row = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id))
        assert row is not None
        if alteration == "consumed":
            row.consumed = True
        else:
            row.plan_digest = "changed"
        session.commit()
    with pytest.raises(ConflictError, match=reason):
        execute(db, plan)
    denied = list_runs(db)[0]
    assert denied.status == "DENIED"
    assert denied.reason == f"ConflictError: {reason}"
    assert len(list_files(db, created.id)) == 3


def test_persisted_plan_tampering_invalidates_digest(db: Database, dataset: DatasetFixture) -> None:
    """Verify persisted plan tampering invalidates digest."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files")
    approve(db, plan)
    with db.session() as session:
        row = session.get(ActionPlanRow, plan.id)
        row.payload = {**row.payload, "external": True}
        session.commit()
    with pytest.raises(ConflictError, match="plan_digest"):
        execute(db, plan)


def test_approved_plan_expires_before_execution(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify approved plan expires before execution."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files", context=ActionContext(ttl_seconds=1))
    approve(db, plan)
    monkeypatch.setattr("datakeel.actions.policy.utcnow", lambda: utcnow() + timedelta(seconds=2))
    with pytest.raises(ConflictError, match="expired"):
        execute(db, plan)


def test_target_revision_change_invalidates_previous_plan(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify target revision change invalidates previous plan."""
    created, _files = dataset
    first = prepare(db, created.id)
    second = prepare(db, created.id)
    execute(db, second)
    with pytest.raises(ConflictError, match="state changed"):
        execute(db, first)


@pytest.mark.usefixtures("dataset")
def test_new_matching_dataset_invalidates_unscoped_frozen_set(db: Database, tmp_path: Path) -> None:
    """Verify new matching dataset invalidates unscoped frozen set."""
    plan = prepare_action(db, "quarantine_files", JsonDocument({"selection": {}}))
    path = tmp_path / "later.txt"
    path.write_text("A later matching fixture")
    import_paths(db, "later", [path])
    with pytest.raises(ConflictError, match="state changed"):
        execute(db, plan)


def test_concurrent_execution_consumes_approval_once(db: Database, dataset: DatasetFixture) -> None:
    """Verify concurrent execution consumes approval once."""
    created, _files = dataset
    plan = prepare(db, created.id, "delete_files")
    approve(db, plan)

    def attempt() -> str:
        """Provide the attempt test fixture."""
        try:
            return execute(db, plan).status
        except ConflictError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: attempt(), range(2)))
    assert sorted(outcomes) == ["REJECTED", "SUCCEEDED"]


@pytest.mark.parametrize(
    ("context", "error"),
    [
        (ActionContext(scopes=[]), AuthorizationError),
        (ActionContext(max_objects=0), BudgetError),
        (ActionContext(max_bytes=0), BudgetError),
    ],
)
def test_prepare_authorization_checks_actual_limits(
    db: Database, dataset: DatasetFixture, context: ActionContext, error: type[Exception]
) -> None:
    """Verify prepare authorization checks actual limits."""
    created, _files = dataset
    with pytest.raises(error):
        prepare(db, created.id, context=context)


def test_truncated_selection_is_never_a_partial_action(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify truncated selection is never a partial action."""
    created, _files = dataset
    with pytest.raises(ValidationError, match="truncated"):
        prepare_action(
            db, "delete_files", JsonDocument({"selection": {"dataset_id": created.id, "limit": 1}})
        )
