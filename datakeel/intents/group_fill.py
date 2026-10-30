# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve group selectors ($tasks, $nth, $files) with read-only queries before planning.

The model describes a group; this module reads it from the project or dataset, so the plan
lists exactly the objects a confirmation changes and the card can say what was left out.
"""

from collections import Counter

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification
from datakeel.intents.catalog import SELF_WORDS, EntityCatalog, candidates
from datakeel.intents.drafts import DraftStep
from datakeel.intents.fill_state import FillState, ask, context_value
from datakeel.intents.selectors import file_selection, ordinal_question, pick
from datakeel.intents.task_scope import CONDITIONS, is_nobody, select_tasks, task_number
from datakeel.intents.verify import says_whole
from datakeel.intents.wording import excluded_text, nothing_to_change, whole_tasks_question
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import task_snapshots

TASK_FIELDS = frozenset({"task_id", "task_ids"})


def _holder(
    spec: dict[str, JsonValue], state: FillState, catalog: EntityCatalog
) -> str | Clarification | None:
    raw = spec.get("holder")
    if not isinstance(raw, str) or not raw.strip() or is_nobody(raw, spec):
        return None
    people = (
        [entry for entry in catalog.of("user") if entry.id == state.actor]
        if raw.strip().casefold() in SELF_WORDS
        else catalog.match("user", raw)
    )
    if len(people) == 1:
        return people[0].id
    step = DraftStep(id="selector", action="assign_tasks")
    asked = ask("holder", step, candidates(people or catalog.of("user")), state.language, raw)
    return asked.model_copy(update={"fields": ["$tasks.holder"]})


def _project(spec: dict[str, JsonValue], state: FillState) -> str | None:
    project = spec.get("project_id") or state.context.project_id or state.focus.get("project_id")
    return project if isinstance(project, str) else None


def nth_package(
    value: JsonValue, project: str | None, state: FillState, catalog: EntityCatalog
) -> str | Clarification:
    """A package by its place in the list (2 or {"$nth": 2}) or by its name."""
    packages = catalog.of("package", project) if project else []
    position = value.get("$nth") if isinstance(value, dict) else value
    if isinstance(position, str) and task_number(position) is None:
        found = catalog.match("package", position, project)
        if len(found) == 1:
            return found[0].id
        step = DraftStep(id="selector", action="assign_tasks")
        return ask("package_id", step, candidates(found or packages), state.language, position)
    number = task_number(position) if isinstance(position, (int, str)) else None
    chosen = pick([entry.id for entry in packages], [number] if number else [])
    return chosen[0] if chosen else ordinal_question("package", state.language)


def _tasks(
    db: Database,
    spec: dict[str, JsonValue],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
) -> tuple[list[str], dict[str, int]] | Clarification:
    holder = _holder(spec, state, catalog)
    if isinstance(holder, Clarification):
        return holder
    project = _project(spec, state)
    if project is None:
        step = DraftStep(id="selector", action=current.action)
        asked = ask("project_id", step, candidates(catalog.of("project")), state.language)
        return asked.model_copy(update={"fields": ["$tasks.project_id"]})
    described = any(key in spec for key in (*CONDITIONS, "numbers", "positions", "first"))
    if not described and not says_whole(state.text):
        # A bare "the tasks" is never widened to every task in the project.
        return Clarification(
            question=whole_tasks_question(state.language),
            action=current.action,
            fields=["$tasks.numbers"],
        )
    package = nth_package(spec["package"], project, state, catalog) if "package" in spec else None
    if isinstance(package, Clarification):
        return package
    scope = select_tasks(
        task_snapshots(db, project),
        spec,
        action=current.action,
        speaker=state.actor,
        found=(holder, package),
    )
    if scope.missing:
        return ordinal_question("task", state.language)
    return scope.ids, scope.excluded


def numbered(field: str, value: JsonValue) -> dict[str, JsonValue] | None:
    """Task numbers written as task ids ("#8", "第 8 个") become a numbers selector.

    A selector the model wrapped in a list (``[{"$tasks": {...}}]``) is the selector itself.
    """
    if field not in TASK_FIELDS:
        return None
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        inner = value[0]
        return inner if "$tasks" in inner else None
    values = value if isinstance(value, list) else [value]
    found = [task_number(item) for item in values if isinstance(item, str)]
    if not values or len(found) != len(values) or None in found:
        return None
    listed: list[JsonValue] = [number for number in found if number is not None]
    return {"$tasks": {"numbers": listed}}


def selector_value(
    db: Database,
    slot: tuple[str, dict[str, JsonValue]],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
    excluded: Counter[str],
) -> JsonValue | Clarification:
    """Resolve the selector in one (field, value) slot; {"$empty": sentence} matches nothing.

    Tasks that protection left out are counted into ``excluded`` for the card.
    """
    field, value = slot
    if "$tasks" in value:
        raw = value["$tasks"]
        found = _tasks(db, raw if isinstance(raw, dict) else {}, current, state, catalog)
        if isinstance(found, Clarification):
            return found
        ids, left_out = found
        excluded.update(left_out)
        if not ids:
            holder = raw.get("holder") if isinstance(raw, dict) else None
            named = "" if is_nobody(holder, {}) else str(holder or "")
            sentence = nothing_to_change("tasks", named, state.language)
            return {"$empty": sentence + excluded_text(left_out, state.language)}
        identifiers: list[JsonValue] = list(ids)
        return identifiers if field.endswith("_ids") else {"$each": identifiers}
    if "$nth" in value:
        return nth_package(value, _project({}, state), state, catalog)
    spec = value["$files"]
    selection = file_selection(
        db,
        spec if isinstance(spec, dict) else {},
        context_value("dataset_id", state, catalog),
        state.context.version_id,
        list(state.context.selected_ids),
    )
    if selection is not None and selection.get("$empty"):
        return {"$empty": nothing_to_change("files", "", state.language)}
    return selection if selection is not None else ask(field, current, [], state.language)
