# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parameters the current state answers: filled from it, never asked of the person.

Each derivable parameter is registered per action with the read that answers it: a review
or a save works on the task's latest revision; taking a task back takes the stage its holder
works in; publishing means the label set's newest version; a project uses the newest
published version. "最新版" or "latest" in a version
field means the same. A task group fanned out over several tasks gets one value per task.
When the state has no answer (a task nothing was saved on), the question says why instead
of asking for an internal value.
"""

import re
from collections.abc import Callable

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError
from datakeel.core.production_models import ProductionTask
from datakeel.intents.drafts import DraftStep
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import latest_label_set, newest_published_version
from datakeel.storage.production_queries import get_task, list_assignments

LATEST_WORDS = frozenset({"latest", "newest", "current", "最新", "最新版", "最新版本", "当前"})
# What the state says, or None when it has no answer (a task nothing was saved on).
type Found = tuple[JsonValue] | None
type Resolver = Callable[[Database, dict[str, JsonValue]], Found]


def _task(db: Database, params: dict[str, JsonValue]) -> ProductionTask | None:
    task = params.get("task_id")
    if not isinstance(task, str):
        return None
    try:
        return get_task(db, task)
    except NotFoundError:
        return None


def _reviewed_revision(db: Database, params: dict[str, JsonValue]) -> Found:
    task = _task(db, params)
    revision = task.latest_revision_id if task is not None else None
    return (revision,) if revision is not None else None


def _previous_revision(db: Database, params: dict[str, JsonValue]) -> Found:
    task = _task(db, params)
    return (task.latest_revision_id,) if task is not None else None


def _held_stage(db: Database, params: dict[str, JsonValue]) -> Found:
    """The stage the current holder works in: taking back a review takes the review."""
    task = _task(db, params)
    held: set[str] = set()
    if task is not None:
        held = {item.stage for item in list_assignments(db, task.id) if item.active}
    return (held.pop(),) if len(held) == 1 else None


def _newest_version(db: Database, params: dict[str, JsonValue]) -> Found:
    label_set = params.get("label_set_id")
    found = latest_label_set(db, label_set) if isinstance(label_set, str) else None
    return (found.version,) if found is not None else None


def _newest_published(db: Database, params: dict[str, JsonValue]) -> Found:
    label_set = params.get("label_set_id")
    version = newest_published_version(db, label_set) if isinstance(label_set, str) else None
    return (version,) if version is not None else None


DERIVED: dict[str, dict[str, Resolver]] = {
    "review_task": {"revision_id": _reviewed_revision},
    "save_revision": {"previous_revision_id": _previous_revision},
    "revoke_assignment": {"stage": _held_stage},
    "release_task": {"stage": _held_stage},
    "publish_label_set": {"version": _newest_version},
    "create_project": {"label_set_version": _newest_published},
}
_UNKNOWN: dict[str, tuple[str, str]] = {
    "revision_id": (
        "这个任务还没有保存过标注, 没有可以审核的内容。",
        "This task has no saved annotation to review yet.",
    ),
    "previous_revision_id": ("没找到这个任务。", "I could not find this task."),
    "version": ("没找到这个标签集。", "I could not find this label set."),
    "label_set_version": (
        "这个标签集还没有发布过的版本, 先发布再用。",
        "This label set has no published version yet; publish it first.",
    ),
}


def derivable(action: str, field: str) -> bool:
    """Whether the state answers this parameter, so it is never asked of the person."""
    return field in DERIVED.get(action, {})


def underivable(field: str, language: str) -> str:
    """Why a parameter the state should answer has no answer: never a question about it."""
    zh, en = _UNKNOWN.get(
        field, ("现在的状态里没有这个值。", "The current state has no value for this.")
    )
    return zh if language == "zh" else en


def _wanted(value: JsonValue) -> bool:
    """Absent, or written as "latest" in words."""
    return value is None or (isinstance(value, str) and value.strip().casefold() in LATEST_WORDS)


def _per_item(db: Database, params: dict[str, JsonValue], resolver: Resolver) -> Found:
    """One value per task when the step runs once per task of a group."""
    group = params.get("task_id")
    each = group.get("$each") if isinstance(group, dict) else None
    if not isinstance(each, list):
        return resolver(db, params)
    found = [resolver(db, {**params, "task_id": item}) for item in each]
    values: list[JsonValue] = [item[0] for item in found if item is not None]
    return ({"$each": values},) if len(values) == len(found) else None


def derive(db: Database, step: DraftStep) -> DraftStep:
    """Fill every derivable parameter the step left out (or wrote as "latest")."""
    resolvers = DERIVED.get(step.action, {})
    params = dict(step.params)
    for field, resolver in resolvers.items():
        if field in params and not _wanted(params[field]):
            continue
        found = _per_item(db, params, resolver)
        if found is not None:
            params[field] = found[0]
        else:
            params.pop(field, None)
    return step.model_copy(update={"params": params})


MODEL_FIELDS = ("id", "name", "version", "provider", "capabilities", "unit_price")


def model_record(step: DraftStep) -> DraftStep:
    """A model registered by name and version: its record is completed, never asked for.

    Fields written beside ``model`` instead of inside it are moved in; the id follows the
    name, the version is text, and a model the platform does not run itself provides
    imported predictions.
    """
    if step.action != "register_model":
        return step
    params = dict(step.params)
    nested = params.get("model")
    record: dict[str, JsonValue] = dict(nested) if isinstance(nested, dict) else {}
    for field in MODEL_FIELDS:
        if field in params:
            record.setdefault(field, params.pop(field))
    name, version = record.get("name"), record.get("version")
    if not isinstance(name, str) or not name.strip():
        return step
    if isinstance(version, int | float) and not isinstance(version, bool):
        record["version"] = str(version)
    record.setdefault("id", re.sub(r"\s+", "-", name.strip().casefold())[:100])
    record.setdefault("provider", "import")
    params["model"] = record
    return step.model_copy(update={"params": params})
