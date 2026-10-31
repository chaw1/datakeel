# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve descriptive selectors to concrete objects before a plan is shown.

A sentence often names a subset rather than ids: "Wang's untouched tasks", "the first two
tasks", "the second package", "the duplicate images". Each selector is resolved here with
bounded read-only queries, in the order the interface shows them, so the plan card lists
exactly the objects a confirmation would change. Anything that cannot be resolved becomes a
question; a selector never widens to the whole dataset or project.
"""

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification, PageContext
from datakeel.core.models import AssetRef
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.object_queries import evaluate

SELECTION_LIMIT = 10000
DUPLICATE_STATUSES = frozenset({"candidate", "accepted"})


def pick(values: list[str], wanted: list[int] | None) -> list[str] | None:
    """Keep the listed positions of an ordered list; None when a position does not exist."""
    if wanted is None:
        return values
    if not wanted or max(wanted) > len(values):
        return None
    return [values[index - 1] for index in wanted]


def _dataset_files(db: Database, dataset_id: str, version_id: str | None) -> list[str]:
    versions = [version_id] if version_id else []
    found = evaluate(
        db, ObjectSet(dataset_id=dataset_id, version_ids=versions, limit=SELECTION_LIMIT)
    )
    return [item.asset_ref.asset_id for item in found.objects]


def named_files(
    db: Database, dataset_id: str, version_id: str | None, names: list[str]
) -> list[str] | None:
    """Files named by their file names; None when any name is not in the dataset."""
    versions = [version_id] if version_id else []
    found = evaluate(
        db, ObjectSet(dataset_id=dataset_id, version_ids=versions, limit=SELECTION_LIMIT)
    )
    by_name: dict[str, str] = {}
    for item in found.objects:
        for key in ("filename", "name", "path"):
            value = item.properties.get(key)
            if isinstance(value, str) and value:
                by_name.setdefault(value.rsplit("/", 1)[-1].casefold(), item.asset_ref.asset_id)
    chosen = [by_name.get(name.strip().rsplit("/", 1)[-1].casefold()) for name in names]
    return None if not chosen or None in chosen else [item for item in chosen if item]


def near_duplicates(db: Database, dataset_id: str, version_id: str | None) -> list[str]:
    """Later copies of each near-duplicate pair; the first file of every group is kept."""
    files = set(_dataset_files(db, dataset_id, version_id))
    copies = {
        item.object.asset_id
        for item in list_assertions(db)
        if item.predicate == "near_duplicate_of"
        and isinstance(item.object, AssetRef)
        and item.status in DUPLICATE_STATUSES
        and item.subject.asset_id in files
        and item.object.asset_id in files
    }
    return sorted(copies)


REST = frozenset({"remaining", "rest", "others", "other", "unselected", "not_selected"})


def _file_ids(
    db: Database,
    spec: dict[str, JsonValue],
    where: tuple[str, str | None],
    selected: list[str],
) -> list[str] | None:
    """The files one ``$files`` kind names; None when the kind cannot be resolved here.

    "The remaining files" are every file of the dataset except the ones selected on the page.
    """
    kind, (dataset_id, version_id) = spec.get("kind"), where
    if kind == "selected":
        return list(selected)
    if kind == "near_duplicates":
        return near_duplicates(db, dataset_id, version_id)
    if kind == "named":
        raw = spec.get("names")
        listed = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
        return named_files(db, dataset_id, version_id, listed)
    if kind in REST and selected:
        chosen = set(selected)
        return [item for item in _dataset_files(db, dataset_id, version_id) if item not in chosen]
    return None


def file_selection(
    db: Database,
    spec: dict[str, JsonValue],
    dataset_id: str | None,
    version_id: str | None,
    selected: list[str],
) -> dict[str, JsonValue] | None:
    """Turn {"$files": {...}} into an exact id selection, or None when it cannot resolve."""
    if dataset_id is None:
        return None
    ids = _file_ids(db, spec, (dataset_id, version_id), selected)
    if ids is None:
        return None
    if not ids:
        return {"dataset_id": dataset_id, "filters": [], "limit": 0, "$empty": True}
    values: list[JsonValue] = list(ids)
    condition: dict[str, JsonValue] = {"field": "id", "operator": "in", "value": values}
    selection: dict[str, JsonValue] = {
        "dataset_id": dataset_id,
        "filters": [condition],
        "limit": len(ids),
    }
    if version_id:
        selection["version_ids"] = [version_id]
    return selection


def ordinal_question(kind: str, language: str) -> Clarification:
    """Ask again when a position does not exist in the list the person sees."""
    zh = {"package": "任务包", "task": "任务"}.get(kind, kind)
    question = (
        f"列表里没有这么多{zh}, 请说具体是哪几个。"
        if language == "zh"
        else f"There are not that many {kind}s in the list; which ones do you mean?"
    )
    return Clarification(question=question, fields=[f"{kind}_id"])


def page_selection(params: dict[str, JsonValue], required: set[str], context: PageContext) -> None:
    """Selected tasks or files on the page fill a missing task or selection parameter."""
    selected: list[JsonValue] = list(context.selected_ids)
    tasks = selected if context.selected_kind == "production_task" else []
    current: list[JsonValue] = tasks or ([context.task_id] if context.task_id else [])
    if "task_id" in required and "task_id" not in params and current:
        params["task_id"] = {"$each": current} if len(current) > 1 else current[0]
    if "task_ids" in required and "task_ids" not in params and current:
        params["task_ids"] = current
    files = selected if context.selected_kind in {None, "file"} else []
    if "selection" in required and "selection" not in params and files:
        condition: dict[str, JsonValue] = {"field": "id", "operator": "in", "value": files}
        params["selection"] = {
            "dataset_id": context.dataset_id,
            "filters": [condition],
            "limit": SELECTION_LIMIT,
        }
