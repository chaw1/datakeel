# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit command-line starts show recoverable approval identities and continue once signed."""

from pathlib import Path

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan
from datakeel.cli import workflow
from datakeel.core.errors import ValidationError
from datakeel.storage.database import Database
from datakeel.storage.workflow_store import get_run, list_runs
from tests.cli.conftest import Invoke
from tests.workflows.conftest import create_dataset


def test_cli_cleanup_prints_plan_url_and_resume_command(
    db: Database,
    tmp_path: Path,
    invoke: Invoke,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Commands exercise the real persisted graph and require a separate human approval."""
    monkeypatch.setattr(workflow, "Database", lambda: db)
    dataset = create_dataset(db, tmp_path / "cli-cleanup")
    invoke(
        "workflow",
        "run",
        "low-quality-cleanup",
        "--input",
        f"dataset_id={dataset.id}",
        "--input",
        "quality_max=0",
        "--idempotency-key",
        "cli-start",
    )
    run = list_runs(db)[0]
    assert run.status == "PAUSED"
    assert run.pending_plan_id is not None
    output = capsys.readouterr().out
    assert f"plan={run.pending_plan_id}" in output
    assert "/#/approvals?plan=" in output
    assert "datakeel workflow resume" in output
    plan = get_plan(db, run.pending_plan_id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    invoke("workflow", "resume", run.id, "--plan", plan.id, "--idempotency-key", "cli-resume")
    assert get_run(db, run.id).status == "SUCCEEDED"
    assert '"conclusion": "cleaned"' in capsys.readouterr().out


def test_cli_inputs_preserve_typed_json_and_reject_duplicate_keys() -> None:
    """Structured overrides remain objects while ordinary dataset identifiers remain strings."""
    assert workflow.inputs(["dataset_id=fixture", 'override={"measure":{"column":"x"}}']).root == {
        "dataset_id": "fixture",
        "override": {"measure": {"column": "x"}},
    }
    for arguments in (["key"], ["=value"], ["key=1", "key=2"]):
        with pytest.raises(ValidationError, match="unique k=v"):
            workflow.inputs(arguments)


def test_cli_reports_failed_run_as_nonzero(
    db: Database,
    invoke: Invoke,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing dataset fails the persisted step and gives a visible command failure."""
    monkeypatch.setattr(workflow, "Database", lambda: db)
    with pytest.raises(SystemExit) as failure:
        invoke("workflow", "run", "dataset-health", "--input", "dataset_id=missing")
    assert failure.value.code == 1
    assert "FAILED" in capsys.readouterr().out
    assert list_runs(db)[0].status == "FAILED"
