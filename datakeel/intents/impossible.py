# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rules execution would refuse, said before a card is made.

A personal-tier project keeps no assignments and no reviews: people work on their tasks
directly and submitted work is approved by the system, so assigning, claiming, taking back,
releasing, renewing or reviewing there would only fail after confirmation, and a review
needs a task that waits for review. The planner says so instead (or sets that part aside
when the rest stands).
"""

from collections.abc import Callable, Sequence

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.intents.capability import model_mismatch
from datakeel.intents.wording import IDLE
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
    "downgrade": (
        "项目档位只能往上升, 不能降回去 (降档会丢掉审核要求)",
        "a project's tier can only go up, never back down (that would drop its review duties)",
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


TIERS = ("personal", "group", "team")


def _upgrade(db: Database, step: ChainStep) -> Found:
    current, wanted = _tier(db, step), step.params.get("workflow_tier")
    if current in TIERS and wanted in TIERS and TIERS.index(wanted) < TIERS.index(current):
        return "downgrade", 0
    return None


RULES: dict[str, Callable[[Database, ChainStep], Found]] = {
    **dict.fromkeys(ASSIGNMENT_ACTIONS, _assignment),
    "review_task": _review,
    "upgrade_project": _upgrade,
}


def _upgraded(db: Database, step: ChainStep, earlier: Sequence[ChainStep]) -> bool:
    """An upgrade earlier in the plan ("先升成小组档, 再派单") lifts the personal rules."""
    raised = [
        item.params.get("project_id")
        for item in earlier
        if item.action == "upgrade_project" and item.params.get("workflow_tier") in TIERS[1:]
    ]
    try:
        with db.session() as session:
            project = project_for_params(session, _concrete(step)) if raised else None
    except (NotFoundError, ValidationError):
        return False
    return project is not None and project in raised


def impossible(
    db: Database, step: ChainStep, language: str, earlier: Sequence[ChainStep] = ()
) -> str | None:
    """Why execution would refuse this step whatever is confirmed, or None.

    ``earlier`` are the plan's steps before this one, which run first.
    """
    mismatch = model_mismatch(db, step, language)
    if mismatch is not None:
        return mismatch
    rule = RULES.get(step.action)
    found = rule(db, step) if rule is not None else None
    if found is None or (found[0].startswith("personal") and _upgraded(db, step, earlier)):
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
    return IDLE[0] if zh else IDLE[1]
