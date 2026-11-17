# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real completion and external rollback through generated lifecycle callbacks."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.action_store import file_handlers
from datakeel.action_store.validation import validate_declarations
from datakeel.actions import file_declarations
from datakeel.actions.declarations import ActionFrame
from datakeel.actions.models import ActionPlan, ExecuteRequest, OperationResult
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.dataset_store.file_state import get_file_state
from datakeel.storage.action_rows import ActionAuditRow, ActionRunRow
from datakeel.storage.database import Database
from tests.actions.conftest import DatasetFixture


def _bind(monkeypatch: pytest.MonkeyPatch, **names: str) -> None:
    declaration, inverse = file_declarations.DECLARATIONS
    handlers = declaration.handlers.model_copy(update=names)
    monkeypatch.setattr(
        file_declarations,
        "DECLARATIONS",
        (declaration.model_copy(update={"handlers": handlers}), inverse),
    )
    validate_declarations()


def _install_completion(
    monkeypatch: pytest.MonkeyPatch, dataset: DatasetFixture, *, failed: bool
) -> list[str]:
    calls: list[str] = []

    def queued(session: Session, frame: ActionFrame) -> ActionFrame:
        frame = file_handlers.quarantine(session, frame)
        return frame.model_copy(update={"result": OperationResult(deferred="fixture-work")})

    def finish(database: Database, plan: ActionPlan, identifier: str) -> OperationResult:
        calls.append(identifier)
        with database.session() as session:
            state = get_file_state(session, dataset[0].id, dataset[1][0].id)
            assert state.quarantined
            assert (
                session.scalar(select(ActionRunRow).where(ActionRunRow.plan_id == plan.id)).status
                == "RUNNING"
            )
        if failed:
            msg = "fixture-completion-refused"
            raise ValidationError(msg)
        return OperationResult(
            outputs=[item.asset_ref for item in plan.manifest.objects],
            details={"committed_state_observed": True},
        )

    monkeypatch.setattr(file_handlers, "queued", queued, raising=False)
    monkeypatch.setattr(file_handlers, "finish", finish, raising=False)
    _bind(monkeypatch, execute="queued", deferred="finish")
    return calls


@pytest.mark.parametrize("failed", [False, True])
def test_deferred_work_observes_commit_and_closes_one_attributed_run(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch, *, failed: bool
) -> None:
    """A callback sees committed state and produces a durable success or failure receipt."""
    calls = _install_completion(monkeypatch, dataset, failed=failed)
    plan = prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset[0].id}})
    )
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    run = execute_plan(db, plan.id, request)
    assert run.status == ("FAILED" if failed else "SUCCEEDED")
    assert run.receipt is not None
    assert run.receipt.run_state == ("FAIL" if failed else "COMPLETED")
    assert run.receipt.quality == (
        {"error": "ValidationError: fixture-completion-refused"}
        if failed
        else {"object_count": 3, "details": {"committed_state_observed": True}}
    )
    assert execute_plan(db, plan.id, request).id == run.id
    assert calls == ["fixture-work"]
    with db.session() as session:
        assert (
            len(list(session.scalars(select(ActionRunRow).where(ActionRunRow.plan_id == plan.id))))
            == 1
        )
        audit = session.scalar(
            select(ActionAuditRow).where(
                ActionAuditRow.plan_id == plan.id, ActionAuditRow.phase == "DEFERRED"
            )
        )
        assert audit.status == run.status


def test_execute_failure_releases_declared_external_resource_before_failure_receipt(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cleanup is a real filesystem effect, while the original error and audit survive."""
    resource = tmp_path / "owned-resource.txt"

    def fail(_session: Session, _frame: ActionFrame) -> ActionFrame:
        resource.write_text("Generated test resource")
        msg = "fixture-execution-refused"
        raise ValidationError(msg)

    def release(_session: Session, frame: ActionFrame) -> ActionFrame:
        resource.unlink()
        return frame

    monkeypatch.setattr(file_handlers, "fail", fail, raising=False)
    monkeypatch.setattr(file_handlers, "release", release, raising=False)
    _bind(monkeypatch, execute="fail", rollback="release")
    plan = prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset[0].id}})
    )
    with pytest.raises(ValidationError, match="fixture-execution-refused"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert not resource.exists()
    with db.session() as session:
        run = session.scalar(select(ActionRunRow).where(ActionRunRow.plan_id == plan.id))
        assert run.status == "FAILED"
        assert run.receipt["run_state"] == "FAIL"
