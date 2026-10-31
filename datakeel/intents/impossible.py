# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rules execution would refuse, said before a card is made.

A personal-tier project keeps no assignments: people work on their tasks directly, so
assigning, claiming, taking back, releasing or renewing a task there would only fail after
confirmation. The planner says so instead (or sets that part aside when the rest stands).
"""

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.storage.database import Database
from datakeel.storage.production_queries import get_project, project_for_params

ASSIGNMENT_ACTIONS = frozenset(
    {"assign_tasks", "claim_task", "revoke_assignment", "release_task", "heartbeat"}
)


def _concrete(step: ChainStep) -> dict[str, JsonValue]:
    params = {key: value for key, value in step.params.items() if not isinstance(value, dict)}
    return {**params, **(step.items[0] if step.items else {})}


def impossible(db: Database, step: ChainStep, language: str) -> str | None:
    """Why execution would refuse this step whatever is confirmed, or None."""
    if step.action not in ASSIGNMENT_ACTIONS:
        return None
    try:
        with db.session() as session:
            project = project_for_params(session, _concrete(step))
        tier = get_project(db, project).workflow_tier if project else None
    except (NotFoundError, ValidationError):
        return None
    if tier != "personal":
        return None
    if language == "zh":
        return "个人档项目不派单, 每个人直接做自己的任务; 要派单得先把项目升级成小组或团队档"
    return (
        "a personal project has no assignments, people work on their tasks directly; "
        "upgrade it to a group or team project to assign work"
    )


def idle_reason(action: str, language: str) -> str:
    """Why a part that would change nothing was left out of the plan."""
    zh = language == "zh"
    if action in {"revoke_assignment", "release_task"}:
        return (
            "这些任务现在没有人领着, 不用收回"
            if zh
            else "nobody holds those tasks, so nothing to take back"
        )
    if action == "assign_tasks":
        return "这些任务已经在这个人手上了" if zh else "those tasks are already with that person"
    return "已经是这样了, 不用改" if zh else "it is already like that"
