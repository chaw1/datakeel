# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise every declared business effect and asynchronous action completion."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Never

import pytest
from sqlalchemy import select

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, list_runs, prepare_action
from datakeel.actions.worker import reconcile_runs
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.storage.action_rows import ApprovalRow
from datakeel.storage.database import Database, DatasetRow, MetadataChangeRow, VersionRow, data_dir
from datakeel.storage.governance_service import save_template
from datakeel.worker.runner import run_worker
from tests.actions.test_service import approve, execute, prepare

if TYPE_CHECKING:
    from tests.actions.conftest import DatasetFixture


def test_create_version_publishes_only_the_frozen_selection(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify create version publishes only the frozen selection."""
    created, files = dataset
    plan = prepare_action(
        db,
        "create_version_from_selection",
        JsonDocument(
            {
                "selection": {
                    "dataset_id": created.id,
                    "filters": [{"field": "id", "operator": "in", "value": [files[1].id]}],
                },
                "name": "one-file-version",
            }
        ),
    )
    result = execute(db, plan)
    version_ref = next(ref for ref in result.receipt.outputs if ref.asset_type == "version")
    with db.session() as session:
        version = session.get(VersionRow, version_ref.asset_id)
        assert [item["id"] for item in version.manifest] == [files[1].id]


def test_metadata_action_uses_schema_validation_and_field_audit(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify metadata action uses schema validation and field audit."""
    created, _files = dataset
    save_template(
        db,
        created.id,
        JsonDocument(
            {
                "schema": {
                    "type": "object",
                    "properties": {"owner": {"type": "string"}},
                    "required": ["owner"],
                }
            }
        ),
    )
    invalid = prepare_action(
        db,
        "save_metadata",
        JsonDocument(
            {
                "dataset_id": created.id,
                "values": {},
                "reason": "invalid generated fixture",
            }
        ),
    )
    with pytest.raises(ValidationError, match="Invalid metadata"):
        execute(db, invalid)
    with db.session() as session:
        assert list(session.scalars(select(MetadataChangeRow))) == []
        assert session.get(DatasetRow, created.id).metadata_values == {}
    valid = prepare_action(
        db,
        "save_metadata",
        JsonDocument(
            {
                "dataset_id": created.id,
                "values": {"owner": "fixture"},
                "reason": "Record ownership",
            }
        ),
    )
    assert execute(db, valid).status == "SUCCEEDED"
    with db.session() as session:
        change = session.scalar(select(MetadataChangeRow))
        assert (change.before, change.after, change.source, change.reason) == (
            None,
            "fixture",
            "action",
            "Record ownership",
        )


@pytest.mark.parametrize("export_format", ["croissant", "openlineage"])
def test_export_requires_approval_and_writes_a_local_artifact(
    db: Database, dataset: DatasetFixture, export_format: str
) -> None:
    """Verify export requires approval and writes a local artifact."""
    created, _files = dataset
    filename = f"reviewed-{export_format}.json"
    plan = prepare_action(
        db,
        "export_dataset",
        JsonDocument(
            {
                "dataset_id": created.id,
                "format": export_format,
                "destination": filename,
            }
        ),
    )
    assert plan.external
    assert plan.requires_approval
    assert not (data_dir() / "exports" / filename).exists()
    approve(db, plan)
    run = execute(db, plan)
    payload = json.loads((data_dir() / "exports" / filename).read_text())
    assert payload
    assert any(ref.asset_id == f"export:{plan.id}" for ref in run.receipt.outputs)


def test_export_failure_consumes_decision_and_records_no_output(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify export failure consumes decision and records no output."""
    created, _files = dataset
    plan = prepare_action(
        db,
        "export_dataset",
        JsonDocument(
            {
                "dataset_id": created.id,
                "destination": "occupied.json",
            }
        ),
    )
    approve(db, plan)
    directory = data_dir() / "exports"
    directory.mkdir()
    (directory / "occupied.json").write_text("Existing user artifact")
    with pytest.raises(ConflictError, match="already exists"):
        execute(db, plan)
    assert (directory / "occupied.json").read_text() == "Existing user artifact"
    failed = list_runs(db)[0]
    assert failed.status == "FAILED"
    assert failed.reason is None
    assert failed.receipt.outputs == []
    with db.session() as session:
        assert session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id)).consumed
    with pytest.raises(ConflictError, match="consumed"):
        execute(db, plan)
    denied = list_runs(db)[0]
    assert denied.status == "DENIED"
    assert denied.reason == "ConflictError: Human approval was already consumed"


@pytest.mark.parametrize(
    "destination", ["../escape.json", "/absolute/escape.json", "nested\\escape.json"]
)
def test_export_destination_cannot_escape_local_exports(
    db: Database, dataset: DatasetFixture, destination: str
) -> None:
    """Verify export destination cannot escape local exports."""
    created, _files = dataset
    with pytest.raises(ValidationError, match="exports directory"):
        prepare_action(
            db,
            "export_dataset",
            JsonDocument(
                {
                    "dataset_id": created.id,
                    "destination": destination,
                }
            ),
        )


def test_pipeline_action_is_completed_by_real_worker_with_one_receipt(
    db: Database, dataset: DatasetFixture
) -> None:
    """Verify pipeline action is completed by real worker with one receipt."""
    created, _files = dataset
    plan = prepare_action(db, "run_pipeline", JsonDocument({"dataset_id": created.id}))
    run = execute(db, plan)
    assert run.status == "QUEUED"
    assert run.receipt is None
    assert run.task_id
    run_worker(db, once=True)
    completed = next(item for item in list_runs(db) if item.id == run.id)
    assert completed.status == "SUCCEEDED"
    assert any(ref.asset_type == "version" for ref in completed.receipt.outputs)
    assert reconcile_runs(db) == 0


def test_failed_pipeline_worker_retains_fail_receipt_without_outputs(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify failed pipeline worker retains fail receipt without outputs."""
    created, _files = dataset
    plan = prepare_action(db, "run_pipeline", JsonDocument({"dataset_id": created.id}))
    run = execute(db, plan)

    def failed(*_args: object) -> Never:
        """Provide the failed test fixture."""
        msg = "Generated worker failure"
        raise OSError(msg)

    monkeypatch.setattr("datakeel.worker.runner.run_pipeline", failed)
    run_worker(db, once=True)
    failed_run = next(item for item in list_runs(db) if item.id == run.id)
    assert failed_run.status == "FAILED"
    assert failed_run.receipt.run_state == "FAIL"
    assert failed_run.receipt.outputs == []


def test_execution_actor_must_match_prepared_actor(db: Database, dataset: DatasetFixture) -> None:
    """Verify execution actor must match prepared actor."""
    created, _files = dataset
    plan = prepare(db, created.id)
    with pytest.raises(AuthorizationError, match="actor"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="another"))
