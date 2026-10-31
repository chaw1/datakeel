# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Query the tasks a sentence describes first, then plan exactly those.

``{"$tasks": {...}}`` describes a group the way people say it: whose tasks, untouched or
not, reworked more than N rounds, in which package, the first or last N, or the numbers the
task list shows ("#8", "第 8 个"). The group is read from the project before any plan is made.
A review-stage assignment only ever takes tasks that wait for review.

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
REVIEW_STATES = frozenset({"submitted", "in_review"})
# Keys a task group may carry; a bare dict of only these is a group the model left unwrapped.
SELECTOR_KEYS = frozenset(
    {*CONDITIONS, "numbers", "positions", "first", "last", "project", "project_id", "include"}
)
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


PLACE_WORDS = re.compile(r"任务包|包|packages?|pkg|\bthe\b|个", re.IGNORECASE)
ORDINAL_WORDS = {
    **{word: index for index, word in enumerate("一二三四五六七八九十", start=1)},
    "两": 2,
    **{
        word: index
        for index, word in enumerate(
            [
                "first",
                "second",
                "third",
                "fourth",
                "fifth",
                "sixth",
                "seventh",
                "eighth",
                "ninth",
                "tenth",
            ],
            start=1,
        )
    },
}


def place_number(value: JsonValue) -> int | None:
    """A place said in words: "第 3 个包", "第三个包", "the third package", "package 3"."""
    number = task_number(value)
    if number is not None or not isinstance(value, str):
        return number
    text = PLACE_WORDS.sub(" ", value).strip()
    number = task_number(text)
    return number or ORDINAL_WORDS.get(text.removeprefix("第").strip().casefold())


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


def _applies(task: TaskSnapshot, action: str, speaker: str, stage: str) -> bool:
    """Tasks the action can act on at all; anything else is not part of the group."""
    if action == "assign_tasks":
        return task.state in (REVIEW_STATES if stage == "review" else OPEN_STATES)
    if action in {"revoke_assignment", "release_task"}:
        held = task.holder is not None and task.stage == stage
        return held and (action != "release_task" or task.holder == speaker)
    return True


def _rounds(spec: dict[str, JsonValue]) -> int:
    value = spec.get("min_rework", spec.get("min_round"))
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _held_by(task: TaskSnapshot, stage: str) -> str | None:
    """Who holds the task in this stage: an annotator while it is open, a reviewer in review."""
    if task.stage != stage:
        return None
    return task.holder if stage != "annotation" or task.state in OPEN_STATES else None


def _matches(
    task: TaskSnapshot,
    spec: dict[str, JsonValue],
    found: tuple[str | None, str | None],
    stage: str,
) -> bool:
    holder, package = found
    if is_nobody(spec.get("holder"), spec) and (task.holder is not None or task.state != "pending"):
        return False
    held_by = _held_by(task, stage)
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
    # A picked "include them too" answer arrives as one comma-joined string.
    listed: list[JsonValue] = (
        raw if isinstance(raw, list) else list(raw.split(",")) if isinstance(raw, str) else []
    )
    unlocked: set[str] = {item for item in listed if isinstance(item, str)} & INCLUDES
    if holder is not None or _rounds(spec):
        unlocked.add("held")
    if _rounds(spec):
        unlocked.add("annotated")
    return unlocked


def _protection(task: TaskSnapshot, guarded: set[str], stage: str) -> str | None:
    # For review only a reviewer's hold counts: the annotator of a submitted task is done.
    held = task.holder is not None and stage in {"annotation", task.stage}
    if held and "held" in guarded:
        return "held"
    if task.annotated and "annotated" in guarded:
        return "annotated"
    return None


def _count(spec: dict[str, JsonValue], key: str) -> int:
    value = spec.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _named(spec: dict[str, JsonValue], total: int) -> list[int] | None:
    """Numbers, or the first / last N said of the whole list, which name those places."""
    named = numbers(spec)
    if named is not None or any(key in spec for key in CONDITIONS):
        return named
    first, last = _count(spec, "first"), _count(spec, "last")
    if first:
        return list(range(1, first + 1))
    return list(range(max(total - last, 0) + 1, total + 1)) if last else None


def select_tasks(
    tasks: list[TaskSnapshot],
    spec: dict[str, JsonValue],
    *,
    action: str,
    speaker: str,
    found: tuple[str | None, str | None] = (None, None),
    stage: str = "annotation",
) -> TaskScope:
    """Resolve one selector over the project's tasks; ``found`` is (holder, package) ids.

    ``stage`` is the step's own: "his review tasks" are the ones he holds for review.
    """
    named = _named(spec, len(tasks))
    if named is not None:
        listed = {task.number: task for task in tasks}
        if any(number not in listed for number in named):
            return TaskScope(missing=True)
        return TaskScope(ids=list(dict.fromkeys(listed[number].id for number in named)))
    holder = found[0]
    group = [
        task
        for task in tasks
        if _applies(task, action, speaker, stage) and _matches(task, spec, found, stage)
    ]
    excluded: Counter[str] = Counter()
    guarded = set(PROTECTIONS.get(action, ())) - _unlocked(spec, holder)
    if stage != "annotation":
        guarded.discard("annotated")  # a task in review is annotated by definition
    kept: list[TaskSnapshot] = []
    for task in group:
        reason = _protection(task, guarded, stage)
        if reason is None:
            kept.append(task)
        else:
            excluded[reason] += 1
    first, last = _count(spec, "first"), _count(spec, "last")
    group = kept[:first] if first else kept[-last:] if last else kept
    return TaskScope(ids=[task.id for task in group], excluded=dict(excluded))
