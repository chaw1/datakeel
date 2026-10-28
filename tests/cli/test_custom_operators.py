# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise the complete local code-review grammar with real approval transactions."""

import json
from pathlib import Path

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan, prepare_action
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.storage.custom_store import list_custom_operators
from datakeel.storage.database import Database
from tests.api.test_custom_operators import CODE
from tests.cli.conftest import Invoke


def test_custom_cli_when_reviewed_publishes_only_the_approved_source(
    invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Submit, inspect, approve and retrieve full source without host execution."""
    source = tmp_path / "operator.py"
    source.write_text(CODE, encoding="utf-8")
    invoke("custom-operator", "submit", str(source), "--name", "cli-example")
    plan = json.loads(capsys.readouterr().out)
    invoke("custom-operator", "review", plan["id"])
    review = json.loads(capsys.readouterr().out)
    assert review["canonical_params"]["code"] == CODE
    invoke("custom-operator", "approve", plan["id"], "--digest", plan["plan_digest"])
    assert json.loads(capsys.readouterr().out)["status"] == "SUCCEEDED"
    invoke("custom-operator", "list")
    version = json.loads(capsys.readouterr().out)[0]
    invoke("custom-operator", "show", version["code_hash"])
    assert json.loads(capsys.readouterr().out)["code"] == CODE
    invoke("custom-operator", "runs")
    assert json.loads(capsys.readouterr().out) == []


def test_custom_cli_when_digest_wrong_refuses_approval(
    invoke: Invoke, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A review decision must bind the displayed immutable plan digest."""
    source = tmp_path / "operator.py"
    source.write_text(CODE, encoding="utf-8")
    invoke("custom-operator", "submit", str(source), "--name", "cli-rejected")
    plan = json.loads(capsys.readouterr().out)
    with pytest.raises(ConflictError):
        invoke("custom-operator", "approve", plan["id"], "--digest", "wrong")
    invoke("custom-operator", "approve", plan["id"], "--digest", plan["plan_digest"], "--reject")
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
    invoke("custom-operator", "list")
    assert json.loads(capsys.readouterr().out) == []


def test_custom_cli_when_already_approved_resumes_once_and_replays_original_run(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lost approval response does not strand the signed source or repeat publication."""
    plan = prepare_action(
        db,
        "submit_custom_operator",
        JsonDocument(
            {
                "name": "cli-recovery",
                "code": CODE,
            }
        ),
    )
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    invoke("custom-operator", "approve", plan.id, "--digest", plan.plan_digest)
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "SUCCEEDED"
    invoke("custom-operator", "approve", plan.id, "--digest", plan.plan_digest)
    replay = json.loads(capsys.readouterr().out)
    assert replay == first
    assert len(list_custom_operators(db)) == 1
    with pytest.raises(ConflictError, match="digest"):
        invoke("custom-operator", "approve", plan.id, "--digest", "wrong")


@pytest.mark.parametrize("executed", [False, True])
def test_custom_cli_when_plan_already_signed_reject_cannot_replace_decision(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str], *, executed: bool
) -> None:
    """Recovery only finishes the original positive decision; it cannot rewrite approval."""
    plan = prepare_action(
        db,
        "submit_custom_operator",
        JsonDocument(
            {
                "name": "cli-fixed-decision",
                "code": CODE,
            }
        ),
    )
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    if executed:
        invoke("custom-operator", "approve", plan.id, "--digest", plan.plan_digest)
        capsys.readouterr()
    with pytest.raises(ConflictError, match=r"decision|execution"):
        invoke("custom-operator", "approve", plan.id, "--digest", plan.plan_digest, "--reject")
    assert get_plan(db, plan.id).status == ("EXECUTED" if executed else "APPROVED")
    assert len(list_custom_operators(db)) == int(executed)
