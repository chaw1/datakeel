# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Starting or widening high-confidence pass-through is a signed change; tightening is not."""

from pathlib import Path

from sqlalchemy import select

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.storage.action_rows import ActionAuditRow
from datakeel.storage.database import Database
from tests.prelabel_support import seed_cloud_project
from tests.production_flow_support import action_payload
from tests.workbench_helpers import run_action


def _plan(db: Database, project_id: str, **values: object) -> tuple[str, str, bool]:
    plan = prepare_action(
        db,
        "configure_project",
        action_payload("configure_project", {"project_id": project_id, **values}),
        ActionContext(actor="local"),
    )
    return plan.id, plan.plan_digest, plan.requires_approval


def _needs_approval(db: Database, project_id: str, **values: object) -> bool:
    return _plan(db, project_id, **values)[2]


def _relaxed_lines(db: Database) -> list[str]:
    with db.session() as session:
        rows = session.scalars(select(ActionAuditRow).where(ActionAuditRow.phase == "PASS_THROUGH"))
        return [str(row.detail["message"]) for row in rows]


def test_a_manual_bar_over_cold_start_and_any_lower_bar_need_approval(
    db: Database, tmp_path: Path
) -> None:
    """Cold start to manual and lowering the bar are signed; raising or clearing it is not."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=1, tier="group")
    # No reviewed objects: thresholds are cold-start defaults and nothing passes through yet.
    assert _needs_approval(db, project.id, confidence_high=0.6)
    assert _needs_approval(db, project.id, confidence_high=0.99)
    assert not _needs_approval(db, project.id, confidence_low=0.2)
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.9})
    assert _needs_approval(db, project.id, confidence_high=0.6)
    assert not _needs_approval(db, project.id, confidence_high=0.95)
    assert not _needs_approval(db, project.id, confidence_high=0.9)
    # Back to cold-start defaults turns pass-through off again, which is stricter.
    assert not _needs_approval(db, project.id, clear=["confidence_thresholds"])


def test_the_audit_names_the_bar_and_who_signed_it(db: Database, tmp_path: Path) -> None:
    """The relaxing change is executed only after approval and the audit names the signer."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=1, tier="group")
    plan_id, digest, required = _plan(db, project.id, confidence_high=0.6)
    assert required
    approve_plan(db, plan_id, ApprovalDecision(approve=True, plan_digest=digest, actor="local"))
    run = execute_plan(db, plan_id, ExecuteRequest(plan_digest=digest, actor="local"))
    assert run.status == "SUCCEEDED"
    (line,) = _relaxed_lines(db)
    assert "未开启（冷启动） → 高档 0.60" in line  # noqa: RUF001  # Chinese punctuation is intended.
    assert "签批人 local" in line
    assert "approved by local" in line
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.8})
    assert len(_relaxed_lines(db)) == 1
