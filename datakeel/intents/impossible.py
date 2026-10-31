# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rules execution would refuse, said before a card is made.

A personal-tier project keeps no assignments and no reviews: people work on their tasks
directly and submitted work is approved by the system, so assigning, claiming, taking back,
releasing, renewing or reviewing there would only fail after confirmation, and a review
needs a task that waits for review. The planner says so instead (or sets that part aside
when the rest stands).
"""

from collections.abc import Callable

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.storage.database import Database
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    project_for_params,
)

ASSIGNMENT_ACTIONS = frozenset(
    {"assign_tasks", "claim_task", "revoke_assignment", "release_task", "heartbeat"}
)
REVIEWABLE = frozenset({"submitted", "in_review"})
REASONS = {
    "personal": (
        "个人档项目不派单, 每个人直接做自己的任务; 要派单得先把项目升级成小组或团队档",
        (
            "a personal project has no assignments, people work on their tasks directly; "
            "upgrade it to a group or team project to assign work"
        ),
    ),
    "personal_review": (
        "个人档项目不审核, 提交后由系统自动通过",
        "a personal project has no reviews; submitted work is approved automatically",
    ),
    "not_submitted": (
        "这条任务还没提交 (或已经审完), 现在不能审核",
        "that task is not waiting for review (not submitted yet, or already reviewed)",
    ),
    "some_not_submitted": (
        "其中 {count} 条任务没在等审核 (还没提交或已经审完), 现在不能审核",
        "{count} of those tasks are not waiting for review (not submitted, or already reviewed)",
    ),
}


def _concrete(step: ChainStep) -> dict[str, JsonValue]:
    params = {key: value for key, value in step.params.items() if not isinstance(value, dict)}
    return {**params, **(step.items[0] if step.items else {})}


def _tier(db: Database, step: ChainStep) -> str | None:
    try:
        with db.session() as session:
            project = project_for_params(session, _concrete(step))
        return get_project(db, project).workflow_tier if project else None
    except (NotFoundError, ValidationError):
        return None


Found = tuple[str, int] | None


def _assignment(db: Database, step: ChainStep) -> Found:
    return ("personal", 0) if _tier(db, step) == "personal" else None


def _review(db: Database, step: ChainStep) -> Found:
    if _tier(db, step) == "personal":
        return "personal_review", 0
    listed = [item.get("task_id") for item in step.items] or [step.params.get("task_id")]
    tasks = [task for task in listed if isinstance(task, str)]
    try:
        waiting = [get_task(db, task).state in REVIEWABLE for task in tasks]
    except NotFoundError:
        return None
    if all(waiting):
        return None
    late = waiting.count(False)
    return ("not_submitted", late) if len(tasks) == 1 else ("some_not_submitted", late)


RULES: dict[str, Callable[[Database, ChainStep], Found]] = {
    **dict.fromkeys(ASSIGNMENT_ACTIONS, _assignment),
    "review_task": _review,
}


def impossible(db: Database, step: ChainStep, language: str) -> str | None:
    """Why execution would refuse this step whatever is confirmed, or None."""
    rule = RULES.get(step.action)
    found = rule(db, step) if rule is not None else None
    if found is None:
        return None
    reason, count = found
    zh, en = REASONS[reason]
    return (zh if language == "zh" else en).format(count=count)


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
