# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Issue actions remain frozen to the exact displayed incident state and capabilities."""

from pathlib import Path

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.dq_reads import read_issues
from datakeel.worker.runner import run_worker
from tests.dq_support import execute_action, generated_rule, save_rule


def test_intervening_failure_invalidates_frozen_issue_claim(db: Database, tmp_path: Path) -> None:
    """A claim cannot silently consume an incident revision updated after preparation."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    execute_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    run_worker(db, once=True)
    issue = read_issues(db)[0]
    params = JsonDocument(
        {
            "issue_id": issue.id,
            "status": "claimed",
            "assignee": "on-call",
            "expected_revision": issue.revision,
        }
    )
    plan = prepare_action(db, "change_quality_issue", params)
    assert not plan.requires_approval
    execute_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    run_worker(db, once=True)
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    current = read_issues(db)[0]
    assert current.revision == issue.revision + 1
    assert current.assignee is None
    with pytest.raises(ConflictError, match="revision changed"):
        prepare_action(db, "change_quality_issue", params)
    execute_action(
        db,
        "change_quality_issue",
        JsonDocument(
            {
                **params.root,
                "expected_revision": current.revision,
            }
        ),
    )
    assert read_issues(db)[0].assignee == "on-call"


def test_retiring_monitoring_invalidates_issue_plan_without_changing_issue_revision(
    db: Database,
    tmp_path: Path,
) -> None:
    """The frozen digest includes a newly available resolution capability."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    execute_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    run_worker(db, once=True)
    issue = read_issues(db)[0]
    plan = prepare_action(
        db,
        "change_quality_issue",
        JsonDocument(
            {
                "issue_id": issue.id,
                "status": "claimed",
                "assignee": "on-call",
                "expected_revision": issue.revision,
            }
        ),
    )
    execute_action(
        db,
        "update_quality_rule",
        JsonDocument(
            {
                "rule": rule.model_copy(update={"enabled": False}).model_dump(mode="json"),
                "expected_revision": 1,
            }
        ),
    )
    current = read_issues(db)[0]
    assert current.revision == issue.revision
    assert current.can_resolve
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    execute_action(
        db,
        "change_quality_issue",
        JsonDocument(
            {
                "issue_id": current.id,
                "status": "resolved",
                "expected_revision": current.revision,
            }
        ),
    )
    assert read_issues(db)[0].status == "resolved"
