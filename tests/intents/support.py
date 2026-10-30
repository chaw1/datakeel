# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated datasets, people and approvals shared by one-sentence regressions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision
from datakeel.core.intent_models import ActionChain, IntentResult, PageContext
from datakeel.intents.chains import advance_chain
from datakeel.intents.planner import PlannerTurn, plan_turn
from datakeel.storage.dataset_service import import_paths
from tests.production_helpers import production_fixture
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.production_models import ProductionTask, Project
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView

SETUP = "给这 5000 张路口图建红绿灯框标注\uff0c两人交叉、抄 10%"
REASSIGN = "把小王手里没动的任务分给小李"
REWORK = "这周谁的返工率最高"
PEOPLE = (("wang", "小王"), ("li", "小李"), ("zhao", "小赵"))


def images(db: Database, directory: Path, count: int = 4, name: str = "路口图") -> DatasetView:
    """Import generated images as one dataset with one version."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"crossing-{index}.png" for index in range(count)]
    for index, path in enumerate(paths):
        Image.new("RGB", (32, 24), (40 + index, 90, 160)).save(path)
    return import_paths(db, name, paths, {"license": "CC0-1.0"})


def plan(
    db: Database,
    text: str,
    context: PageContext | None = None,
    actor: str = "local",
    pending: IntentResult | None = None,
) -> IntentResult:
    """Plan one sentence with rules only and require a decision."""
    result = plan_turn(
        db, PlannerTurn(text=text, actor=actor, context=context or PageContext(), pending=pending)
    )
    assert result is not None
    return result


def approve_waiting(db: Database, chain: ActionChain, actor: str = "local") -> None:
    """Sign every plan of the step the chain is waiting on, as the approval queue would."""
    step = next(item for item in chain.steps if item.status == "awaiting_approval")
    for plan_id in step.plan_ids:
        current = service.get_plan(db, plan_id)
        service.approve_plan(
            db,
            plan_id,
            ApprovalDecision(approve=True, plan_digest=current.plan_digest, actor=actor),
        )


def run_to_end(db: Database, chain: ActionChain, actor: str = "local") -> ActionChain:
    """Confirm, sign each waiting step and continue until the chain stops for another reason."""
    current = advance_chain(db, chain.id, actor)
    while current.status == "awaiting_approval":
        approve_waiting(db, current, actor)
        current = advance_chain(db, chain.id, actor)
    return current


def team(db: Database) -> tuple[Project, tuple[ProductionTask, ...]]:
    """A group project whose manager is boss and whose annotator wang holds two tasks."""
    project, tasks = production_fixture(db, "group", count=3)
    runner = ServiceRunner(db)
    runner("manage_users", {"operation": "create", "user_id": "boss", "display_name": "老板"})
    for user, name in PEOPLE:
        runner(
            "manage_users", {"operation": "create", "user_id": user, "display_name": name}, "boss"
        )
        runner(
            "manage_users",
            {
                "operation": "bind_role",
                "user_id": user,
                "role_id": "annotator",
                "project_id": project.id,
            },
            "boss",
        )
    runner("assign_tasks", {"task_ids": [tasks[0].id, tasks[1].id], "actor": "wang"}, "boss")
    return project, tasks
