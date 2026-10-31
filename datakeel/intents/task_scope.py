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
# Conditions on the tasks themselves; a package is a place, not a condition.
FILTERS = frozenset(CONDITIONS) - {"package"}
FROM_END = re.compile(r"倒数第|从后往前数?第|from the (?:end|bottom)|\bto[- ]last\b", re.IGNORECASE)


# Whose tasks: one person, the members of a named team ("码头组的人"), or anyone.
type Holder = str | frozenset[str] | None


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
    if action in {"revoke_assignment", "release_task", "heartbeat"}:
        held = task.holder is not None and task.stage == stage
        return held and (action == "revoke_assignment" or task.holder == speaker)
    if action == "submit_task":
        # Only an open task with saved work can be handed in.
        return task.annotated and task.state in OPEN_STATES
    # Only a task handed in and not yet decided can be reviewed.
    return action != "review_task" or task.state in REVIEW_STATES


def _rounds(spec: dict[str, JsonValue]) -> int:
    value = spec.get("min_rework", spec.get("min_round"))
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _held_by(task: TaskSnapshot, stage: str) -> str | None:
    """Who holds the task in this stage: an annotator while it is open, a reviewer in review."""
    if stage == "read":
        return task.holder
    if task.stage != stage:
        return None
    return task.holder if stage != "annotation" or task.state in OPEN_STATES else None


def _matches(
    task: TaskSnapshot,
    spec: dict[str, JsonValue],
    found: tuple[Holder, str | None],
    stage: str,
) -> bool:
    holder, package = found
    if is_nobody(spec.get("holder"), spec) and (task.holder is not None or task.state != "pending"):
        return False
    # In review, on a task nobody holds, or in a read, "Mia's task" is also one she annotated.
    own = stage in {"review", "read"} or (task.holder is None and task.state in OPEN_STATES)
    whose = {_held_by(task, stage), task.annotator if own else None}
    wanted = {holder} if isinstance(holder, str) else holder
    if wanted is not None and not whose & wanted:
        return False
    state = spec.get("state")
    checks = (
        spec.get("untouched") is True and task.annotated,
        task.round < _rounds(spec),
        isinstance(state, str) and task.state != state,
        package is not None and task.package_id != package,
    )
    return not any(checks)


def _unlocked(spec: dict[str, JsonValue], holder: Holder) -> set[str]:
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


def from_end(spec: dict[str, JsonValue], text: str) -> dict[str, JsonValue]:
    """One task counted from the end ("倒数第二条", "second to last"), not the last two."""
    back = _count(spec, "last")
    if not back or not FROM_END.search(text):
        return spec
    return {**{key: value for key, value in spec.items() if key != "last"}, "from_end": back}


def _places(listed: list[int], spec: dict[str, JsonValue]) -> list[int] | None:
    first, last, back = _count(spec, "first"), _count(spec, "last"), _count(spec, "from_end")
    if back:
        return [listed[-back] if back <= len(listed) else 0]
    return listed[:first] if first else listed[-last:] if last else None


def _named(
    tasks: list[TaskSnapshot], spec: dict[str, JsonValue], package: str | None
) -> list[int] | None:
    """Numbers, or the first / last N said of a list, which name those places.

    Within a named package a place counts in that package ("包 2 的第 2 个"), while a list
    number that lies in the package is that task. Places are taken as said.
    """
    named = numbers(spec)
    if any(key in spec for key in FILTERS):
        return named
    inside = [task.number for task in tasks if package is None or task.package_id == package]
    if named is not None and package is not None:
        return [n if n in inside else inside[n - 1] if n <= len(inside) else 0 for n in named]
    return named if named is not None else _places(inside, spec)


def _taken_as_said(named: list[TaskSnapshot], action: str, stage: str) -> TaskScope:
    """Named tasks are taken as said; for assigning, ones already handed in are left out."""
    unique = list({task.id: task for task in named}.values())
    if action != "assign_tasks":
        return TaskScope(ids=[task.id for task in unique])
    allowed = REVIEW_STATES if stage == "review" else OPEN_STATES
    kept = [task.id for task in unique if task.state in allowed]
    closed = len(unique) - len(kept)
    return TaskScope(ids=kept, excluded={"closed": closed} if closed else {})


def select_tasks(
    tasks: list[TaskSnapshot],
    spec: dict[str, JsonValue],
    *,
    action: str,
    speaker: str,
    found: tuple[Holder, str | None] = (None, None),
    stage: str = "annotation",
) -> TaskScope:
    """Resolve one selector over the project's tasks; ``found`` is (holder, package) ids.

    ``stage`` is the step's own: "his review tasks" are the ones he holds for review.
    """
    said = numbers(spec)
    if said is not None and any(key in spec for key in FILTERS):
        # "没人领的任务, 第 2 和第 3 条": numbers outside the group are places in it.
        described = [task for task in tasks if _applies(task, action, speaker, stage)]
        described = [task for task in described if _matches(task, spec, found, stage)]
        inside = {task.number for task in described}
        if not all(n in inside for n in said) and all(n <= len(described) for n in said):
            return TaskScope(ids=[described[n - 1].id for n in said])
        # "#5 到 #8 里没人领的": numbers that are not places narrow the group to those numbers.
        both = [task.id for task in described if task.number in said]
        if both and len(both) < len(said):
            return TaskScope(ids=both)
    named = _named(tasks, spec, found[1])
    if named is not None:
        listed = {task.number: task for task in tasks}
        if any(number not in listed for number in named):
            return TaskScope(missing=True)
        return _taken_as_said([listed[number] for number in named], action, stage)
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
    if any(_count(spec, key) for key in ("first", "last", "from_end")):
        return _located(group, spec, guarded, (action, stage))
    kept: list[TaskSnapshot] = []
    for task in group:
        reason = _protection(task, guarded, stage)
        if reason is None:
            kept.append(task)
        else:
            excluded[reason] += 1
    return TaskScope(ids=[task.id for task in kept], excluded=dict(excluded))


def _located(
    group: list[TaskSnapshot], spec: dict[str, JsonValue], guarded: set[str], step: tuple[str, str]
) -> TaskScope:
    """The first or last N are counted in the list as shown, before any protection.

    Protection never moves the place to another task: a located task it would have left
    out is taken as said, and the card says so ("kept_*").
    """
    first, last, back = _count(spec, "first"), _count(spec, "last"), _count(spec, "from_end")
    located = group[:first] if first else group[-last:] if last else group[-back:][:1]
    scope = _taken_as_said(located, *step)
    warned = Counter(
        f"kept_{reason}"
        for task in located
        if task.id in scope.ids and (reason := _protection(task, guarded, step[1])) is not None
    )
    return scope.model_copy(update={"excluded": {**scope.excluded, **warned}})
