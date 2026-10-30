# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Query the tasks a sentence describes first, then plan exactly those.

``{"$tasks": {...}}`` describes a group the way people say it: whose tasks, untouched or
not, reworked more than N rounds, in which package, the first N, or the numbers the task
list shows ("#8", "第 8 个"). The group is read from the project before any plan is made.

Writes on a described group leave out, by default, tasks someone else holds and tasks with
saved human annotation: the words must ask for them ("已经标了的也收", a named holder, a
rework count). Numbered tasks are named one by one and are taken as said. What was left out
is counted for the card, so the person sees why the plan is smaller than the group.
"""

import re
from collections import Counter

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel
from datakeel.storage.intent_reads import TaskSnapshot

# What each write leaves out of a described group unless the words ask for it. Revoking
# is always about held tasks, so only saved annotation protects a task from it.
PROTECTIONS = {
    "assign_tasks": ("held", "annotated"),
    "revoke_assignment": ("annotated",),
}
CONDITIONS = ("holder", "unassigned", "untouched", "min_rework", "min_round", "package", "state")
OPEN_STATES = frozenset({"pending", "in_progress"})
NOBODY = frozenset(
    {"nobody", "none", "unassigned", "no one", "没人", "无人", "没有人", "未分配", "没人领"}
)
NUMBER = re.compile(r"^\s*(?:#|第|no\.?\s*)?\s*(\d{1,5})\s*(?:个|条|号)?\s*$", re.IGNORECASE)
INCLUDES = frozenset({"held", "annotated"})


class TaskScope(BoundaryModel):
    """The tasks a selector names, what protection left out, or a number that is not listed."""

    ids: list[str] = Field(default_factory=list[str])
    excluded: dict[str, int] = Field(default_factory=dict[str, int])
    missing: bool = False


def task_number(value: JsonValue) -> int | None:
    """8, "8", "#8" or "第 8 个" as the task list's number; None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    match = NUMBER.match(value) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def numbers(spec: dict[str, JsonValue]) -> list[int] | None:
    """Numbers the person named; ``positions`` is the older spelling of the same thing."""
    raw = spec.get("numbers", spec.get("positions"))
    if not isinstance(raw, list) or not raw:
        return None
    found = [task_number(item) for item in raw]
    return [item for item in found if item is not None] or None


def is_nobody(holder: JsonValue, spec: dict[str, JsonValue]) -> bool:
    """Unassigned tasks: said as a holder word or as ``unassigned: true``."""
    word = holder.strip().casefold() if isinstance(holder, str) else ""
    return spec.get("unassigned") is True or word in NOBODY


def _applies(task: TaskSnapshot, action: str, speaker: str) -> bool:
    """Tasks the action can act on at all; anything else is not part of the group."""
    if action == "assign_tasks":
        return task.state in OPEN_STATES
    if action in {"revoke_assignment", "release_task"}:
        held = task.holder is not None and task.stage == "annotation"
        return held and (action != "release_task" or task.holder == speaker)
    return True


def _rounds(spec: dict[str, JsonValue]) -> int:
    value = spec.get("min_rework", spec.get("min_round"))
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _matches(
    task: TaskSnapshot, spec: dict[str, JsonValue], holder: str | None, package: str | None
) -> bool:
    if is_nobody(spec.get("holder"), spec) and (task.holder is not None or task.state != "pending"):
        return False
    held_by = task.holder if task.stage == "annotation" and task.state in OPEN_STATES else None
    if holder is not None and held_by != holder:
        return False
    state = spec.get("state")
    checks = (
        spec.get("untouched") is True and task.annotated,
        task.round < _rounds(spec),
        isinstance(state, str) and task.state != state,
        package is not None and task.package_id != package,
    )
    return not any(checks)


def _unlocked(spec: dict[str, JsonValue], holder: str | None) -> set[str]:
    """Protections the words lift: a named holder, a rework count, or an explicit include."""
    raw = spec.get("include")
    listed: list[JsonValue] = raw if isinstance(raw, list) else []
    unlocked: set[str] = {item for item in listed if isinstance(item, str)} & INCLUDES
    if holder is not None or _rounds(spec):
        unlocked.add("held")
    if _rounds(spec):
        unlocked.add("annotated")
    return unlocked


def _protection(task: TaskSnapshot, guarded: set[str]) -> str | None:
    if task.holder is not None and "held" in guarded:
        return "held"
    if task.annotated and "annotated" in guarded:
        return "annotated"
    return None


def _named(spec: dict[str, JsonValue]) -> list[int] | None:
    """Numbers, or "the first N" said of the whole list, which names the list's first N."""
    named = numbers(spec)
    first = spec.get("first")
    plain = not any(key in spec for key in CONDITIONS)
    if named is None and plain and isinstance(first, int) and not isinstance(first, bool):
        return list(range(1, first + 1)) if first > 0 else None
    return named


def select_tasks(
    tasks: list[TaskSnapshot],
    spec: dict[str, JsonValue],
    *,
    action: str,
    speaker: str,
    found: tuple[str | None, str | None] = (None, None),
) -> TaskScope:
    """Resolve one selector over the project's tasks; ``found`` is (holder, package) ids."""
    named = _named(spec)
    if named is not None:
        listed = {task.number: task for task in tasks}
        if any(number not in listed for number in named):
            return TaskScope(missing=True)
        return TaskScope(ids=list(dict.fromkeys(listed[number].id for number in named)))
    holder, package = found
    group = [
        task
        for task in tasks
        if _applies(task, action, speaker) and _matches(task, spec, holder, package)
    ]
    excluded: Counter[str] = Counter()
    guarded = set(PROTECTIONS.get(action, ())) - _unlocked(spec, holder)
    kept: list[TaskSnapshot] = []
    for task in group:
        reason = _protection(task, guarded)
        if reason is None:
            kept.append(task)
        else:
            excluded[reason] += 1
    group = kept
    first = spec.get("first")
    if isinstance(first, int) and not isinstance(first, bool) and first > 0:
        group = group[:first]
    return TaskScope(ids=[task.id for task in group], excluded=dict(excluded))
