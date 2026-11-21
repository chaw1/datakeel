# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI tests for workflow listing, validation, run history, inspection and JSON output."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, cast

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan
from datakeel.cli import workflow as workflow_cli
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.runtime.workflow_service import resume_workflow
from tests.workflows.conftest import worker_hooks

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.cli.parsers import CommandGroup
    from datakeel.datasets.views import DatasetView
    from datakeel.storage.database import Database


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="datakeel")
    commands = cast("CommandGroup", parser.add_subparsers(dest="command", required=True))
    workflow_cli.register_parser(commands)
    return parser.parse_args(["workflow", *argv])


def test_workflow_cli_list_and_validate_json_and_human(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """List and validate support both human-readable lines and structured JSON."""
    workflow_cli.dispatch(_parse("list"))
    assert "low-quality-cleanup:" in capsys.readouterr().out

    workflow_cli.dispatch(_parse("list", "--json"))
    definitions = json.loads(capsys.readouterr().out)
    assert any(item["id"] == "low-quality-cleanup" for item in definitions)

    bad = tmp_path / "invalid.yaml"
    bad.write_text("id: broken\nsteps: []\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        workflow_cli.dispatch(_parse("validate", str(bad), "--json"))
    assert exc.value.code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["valid"] is False
    assert report["errors"]


def test_workflow_cli_paused_run_history_show_audit_and_resume(
    db: Database,
    dataset: DatasetView,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run, list runs, show timeline/audit, enforce actor isolation and resume cleanly."""
    monkeypatch.setattr(workflow_cli, "Database", lambda: db)
    monkeypatch.setattr(workflow_cli, "require_current", lambda _db: None)
    monkeypatch.setattr(db.engine, "dispose", lambda: None)

    workflow_cli.dispatch(
        _parse(
            "run",
            "low-quality-cleanup",
            "--input",
            f"dataset_id={dataset.id}",
            "--input",
            "quality_max=60",
            "--idempotency-key",
            "cli-cleanup-1",
            "--json",
        )
    )
    paused = json.loads(capsys.readouterr().out)
    run_id = str(paused["id"])
    plan_id = str(paused["pending_plan_id"])
    assert paused["status"] == "PAUSED"

    workflow_cli.dispatch(_parse("runs", "--workflow", "low-quality-cleanup", "--status", "PAUSED"))
    runs_out = capsys.readouterr().out
    assert run_id in runs_out
    assert "PAUSED" in runs_out

    workflow_cli.dispatch(_parse("runs", "--limit", "1", "--json"))
    listed_json = json.loads(capsys.readouterr().out)
    assert len(listed_json) == 1
    assert listed_json[0]["id"] == run_id

    with pytest.raises(ValidationError, match="at least 1"):
        workflow_cli.dispatch(_parse("runs", "--limit", "0"))

    with pytest.raises(AuthorizationError):
        workflow_cli.dispatch(_parse("show", run_id, "--actor", "other-actor"))

    workflow_cli.dispatch(_parse("show", run_id))
    shown_text = capsys.readouterr().out
    assert f"run={run_id}" in shown_text
    assert f"plan={plan_id}" in shown_text
    assert "[PAUSED]" in shown_text
    monkeypatch.setattr(
        workflow_cli,
        "resume_workflow",
        lambda d, rid, req, *, actor="local": resume_workflow(
            d, rid, req, hooks=worker_hooks(d), actor=actor
        ),
    )
    _verify_audit_and_resume(db, run_id, plan_id, capsys)


def _verify_audit_and_resume(
    db: Database,
    run_id: str,
    plan_id: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(AuthorizationError):
        workflow_cli.dispatch(_parse("resume", run_id, "--plan", plan_id))

    workflow_cli.dispatch(_parse("show", run_id, "--audit", "--json"))
    with_audit = json.loads(capsys.readouterr().out)
    assert with_audit["run"]["id"] == run_id
    assert len(with_audit["audit"]) >= 1

    workflow_cli.dispatch(_parse("show", run_id, "--audit"))
    assert "audit=RESUME_DENIED" in capsys.readouterr().out

    plan_digest = get_plan(db, plan_id).plan_digest
    approve_plan(db, plan_id, ApprovalDecision(approve=True, plan_digest=plan_digest))
    workflow_cli.dispatch(_parse("resume", run_id, "--plan", plan_id))
    resumed_out = capsys.readouterr().out
    assert "status=SUCCEEDED" in resumed_out
