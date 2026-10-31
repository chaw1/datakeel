# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A read that names no project: the speaker's only project, said aloud, or a choice.

"How many do I have left?" on a page without a project is answered for the one project the
speaker works in, and the answer starts with 「按你所在的「X」项目」 so the assumption is
visible. A speaker in several projects is asked, with those projects to pick from.

A read about one task said by its number ("第 4 个任务现在在谁手上") reads that task: the
number is counted in the read's project like everywhere else, however the model wrote it.
"""

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification
from datakeel.intents.catalog import FIELD_KINDS, CatalogEntry, EntityCatalog, candidates
from datakeel.intents.group_fill import numbered
from datakeel.intents.wording import field_label
from datakeel.storage.database import Database
from datakeel.storage.identity_store import get_bindings


def own_projects(db: Database, actor: str, catalog: EntityCatalog) -> list[CatalogEntry]:
    """Projects the speaker is bound to; with no binding, every project (an administrator)."""
    bound = {binding.project_id for binding in get_bindings(db, actor) if binding.project_id}
    projects = catalog.of("project")
    mine = [entry for entry in projects if entry.id in bound]
    return mine or projects


def assumed_note(entry: CatalogEntry, language: str) -> str:
    """The visible assumption an answer starts with."""
    if language == "zh":
        return f"按你所在的「{entry.label}」项目: "
    return f'For your project "{entry.label}": '


def scope_question(
    action: str, missing: list[str], language: str, choices: list[CatalogEntry]
) -> Clarification:
    """Ask for the missing scope, offering the speaker's own choices."""
    names = "、".join(field_label(item, language) for item in missing)
    question = (
        f"要回答这个问题, 还缺: {names}。请选一个。"
        if language == "zh"
        else f"I need: {names}. Please pick one."
    )
    return Clarification(
        question=question, action=action, fields=missing, candidates=candidates(choices)
    )


def missing_choices(field: str, catalog: EntityCatalog) -> list[CatalogEntry]:
    """Objects that could fill one missing read parameter."""
    kind = FIELD_KINDS.get(field)
    return catalog.of(kind) if kind and kind != "task" else []


def _leaves(value: JsonValue) -> list[str]:
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _leaves(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _leaves(item)]
    return [str(value)] if isinstance(value, str | int | float) else []


def unfiltered_note(
    unknown: dict[str, JsonValue], text: str, language: str, applied: frozenset[str] = frozenset()
) -> str:
    """Say which condition the read could not apply, in the person's own words.

    ``applied`` are names the read did use another way (a project named in the sentence).
    """
    leaves = [leaf for leaf in _leaves(unknown) if leaf not in applied]
    if not unknown or (applied and not leaves):
        return ""
    said = [leaf for leaf in leaves if leaf and leaf in text]
    named = "、".join(f"「{item}」" for item in dict.fromkeys(said))
    if language == "zh":
        condition = f"按{named}" if named else "按你说的条件"
        return f" (这个查询不能{condition}筛选, 上面是不加这个条件的结果。)"
    condition = f"by {', '.join(dict.fromkeys(said))}" if said else "by what you asked"
    return f" (This read cannot filter {condition}; the answer above is unfiltered.)"


def _task_said(value: JsonValue) -> bool:
    return numbered("task_id", value) is not None or (isinstance(value, dict) and "$tasks" in value)


def task_argument(
    known: dict[str, JsonValue], unknown: dict[str, JsonValue], fields: set[str]
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """A task the model put under a made-up key ("tasks") is the read's task_id."""
    if "task_id" not in fields or "task_id" in known:
        return known, unknown
    key = next((name for name, item in unknown.items() if _task_said(item)), None)
    if key is None:
        return known, unknown
    rest = {name: item for name, item in unknown.items() if name != key}
    return {**known, "task_id": unknown[key]}, rest


def one_task(params: dict[str, JsonValue], language: str) -> dict[str, JsonValue] | Clarification:
    """A read takes one task: a group of exactly one is that task, a larger one is asked."""
    value = params.get("task_id")
    listed = value.get("$each") if isinstance(value, dict) else None
    if not isinstance(listed, list):
        return params
    if len(listed) == 1:
        return {**params, "task_id": listed[0]}
    question = (
        "这个查询一次只看一个任务, 要看哪一个?"
        if language == "zh"
        else "This read looks at one task at a time; which one?"
    )
    return Clarification(question=question, fields=["task_id"])
