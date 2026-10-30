# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fill identities from the sentence, the page and the previous turn, never by guessing.

Identity values are resolved against the catalog; one match is used, several become a
choice (the object on the page wins), none becomes a question. "I/me" is the speaker. Only
container objects (dataset, version, project) may default to the page or the previous
turn, and only reads also to a single existing object. A container a write names must be
grounded in the page, the previous turn or the person's words (see ``grounding``).
Parameters the action does not have are reported, never dropped silently.
"""

from pydantic import Field, JsonValue

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.intent_models import Candidate, Clarification, PageContext
from datakeel.core.models import BoundaryModel, new_id
from datakeel.intents.catalog import (
    FIELD_KINDS,
    LIST_KINDS,
    SELF_WORDS,
    CatalogEntry,
    EntityCatalog,
    candidates,
)
from datakeel.intents.drafts import DraftStep
from datakeel.intents.edits import prepare_label_edit
from datakeel.intents.grounding import grounded
from datakeel.intents.selectors import (
    file_selection,
    ordinal_question,
    pick,
    positions,
    project_tasks,
)
from datakeel.intents.wording import field_label, nothing_to_change, unknown_question
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.storage.database import Database

CONTAINERS = ("dataset_id", "version_id", "project_id", "package_id", "label_set_id")
SINGLE_DEFAULTS = frozenset({"dataset_id", "project_id"})
SELECTION_LIMIT = 10000
TASK_PLURALS = {"task_ids": "task_id", "task_id": "task_ids"}
# Intent-only spellings of an edit that ``prepare_label_edit`` turns into the full list.
EDIT_KEYS = {"create_label_set": frozenset({"add_labels", "remove_labels"})}


class FillState(BoundaryModel):
    """Values available to every step: page context and the previous turn's objects."""

    context: PageContext = Field(default_factory=PageContext)
    focus: dict[str, str] = Field(default_factory=dict[str, str])
    actor: str = "local"
    language: str = "zh"
    text: str = ""


class FillResult(BoundaryModel):
    """Filled steps, or the first question that has to be answered before planning."""

    steps: list[DraftStep] = Field(default_factory=list[DraftStep])
    clarification: Clarification | None = None
    empty_selection: str | None = None


def _ask(
    field: str, step: DraftStep, choices: list[Candidate], language: str, mention: str = ""
) -> Clarification:
    label = field_label(field, language)
    if language == "zh":
        question = (
            f"「{mention}」对应多个{label}, 是哪一个?"
            if mention and len(choices) > 1
            else f"没找到叫「{mention}」的{label}, 是下面哪一个?"
            if mention and choices
            else f"没找到叫「{mention}」的{label}, 换个说法试试?"
            if mention
            else f"是哪个{label}?"
        )
    else:
        question = (
            f'"{mention}" matches several; which {label}?'
            if mention and len(choices) > 1
            else f'No {label} is called "{mention}"; is it one of these?'
            if mention and choices
            else f'No {label} is called "{mention}"; could you rephrase?'
            if mention
            else f"Which {label}?"
        )
    return Clarification(question=question, action=step.action, fields=[field], candidates=choices)


def context_value(field: str, state: FillState, catalog: EntityCatalog) -> str | None:
    """The page's (or the previous turn's) object for one container field."""
    context = state.context
    value: str | None = getattr(context, field, None)
    if value is None and field == "dataset_id" and context.version_id:
        version = catalog.get("version", context.version_id)
        value = version.parent if version else None
    if value is None and field == "dataset_id" and context.project_id:
        project = catalog.get("project", context.project_id)
        value = project.parent if project else None
    return value or state.focus.get(field)


def _default_container(
    field: str,
    params: dict[str, JsonValue],
    state: FillState,
    catalog: EntityCatalog,
    *,
    single: bool,
) -> str | None:
    value = context_value(field, state, catalog)
    if value is not None:
        return value
    if field == "version_id":
        dataset = params.get("dataset_id")
        versions = catalog.of("version", dataset if isinstance(dataset, str) else None)
        return versions[-1].id if isinstance(dataset, str) and versions else None
    if not single or field not in SINGLE_DEFAULTS:
        return None
    pool = catalog.of(FIELD_KINDS[field])
    return pool[0].id if len(pool) == 1 else None


def _page_first(found: list[CatalogEntry], page: str | None) -> list[CatalogEntry]:
    on_page = [entry for entry in found if entry.id == page]
    return on_page or found


def _resolve_identity(
    field: str, value: str, step: DraftStep, state: FillState, catalog: EntityCatalog
) -> str | Clarification:
    kind = FIELD_KINDS[field]
    if kind == "task":
        return value
    if kind == "user" and value.strip().casefold() in SELF_WORDS:
        return state.actor
    parent = None
    if kind == "version":
        dataset = step.params.get("dataset_id")
        parent = dataset if isinstance(dataset, str) else None
    page = context_value(field, state, catalog) if field in CONTAINERS else None
    found = _page_first(catalog.match(kind, value, parent), page)
    said = step.said.get(field)
    only = step.action in PARAMETER_MODELS and len(catalog.of(kind, parent)) == 1
    if len(found) == 1 and (only or grounded(field, found[0], state.text, page, said)):
        return found[0].id
    if len(found) == 1:
        # Named by nobody: the model copied it from the catalog, so ask instead of guessing.
        return _ask(field, step, candidates(catalog.of(kind, parent)), state.language)
    pool = found or catalog.of(kind, parent)
    return _ask(field, step, candidates(pool), state.language, said or value)


def _resolve_list(
    field: str, values: list[JsonValue], step: DraftStep, state: FillState, catalog: EntityCatalog
) -> list[JsonValue] | Clarification:
    kind = LIST_KINDS[field]
    resolved: list[JsonValue] = []
    for value in values:
        if not isinstance(value, str):
            resolved.append(value)
            continue
        found = catalog.match(kind, value)
        if len(found) != 1:
            return _ask(field, step, candidates(found or catalog.of(kind)), state.language, value)
        resolved.append(found[0].id)
    return resolved


def _holder(raw: JsonValue, state: FillState, catalog: EntityCatalog) -> str | Clarification | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    people = (
        [entry for entry in catalog.of("user") if entry.id == state.actor]
        if raw.strip().casefold() in SELF_WORDS
        else catalog.match("user", raw)
    )
    if len(people) == 1:
        return people[0].id
    step = DraftStep(id="selector", action="assign_tasks")
    asked = _ask("holder", step, candidates(people or catalog.of("user")), state.language, raw)
    return asked.model_copy(update={"fields": ["$tasks.holder"]})


def _tasks(
    db: Database, selector: dict[str, JsonValue], state: FillState, catalog: EntityCatalog
) -> list[str] | Clarification:
    holder = _holder(selector.get("holder"), state, catalog)
    if isinstance(holder, Clarification):
        return holder
    project = (
        selector.get("project_id") or state.context.project_id or state.focus.get("project_id")
    )
    if not isinstance(project, str):
        step = DraftStep(id="selector", action="assign_tasks")
        asked = _ask("project_id", step, candidates(catalog.of("project")), state.language)
        return asked.model_copy(update={"fields": ["$tasks.project_id"]})
    untouched = selector.get("untouched") is True
    found = project_tasks(db, project, holder=holder, untouched=untouched, open_only=True)
    chosen = pick(found, positions(selector))
    return ordinal_question("task", state.language) if chosen is None else chosen


def _nth_package(
    value: dict[str, JsonValue], state: FillState, catalog: EntityCatalog
) -> str | Clarification:
    project = state.context.project_id or state.focus.get("project_id")
    packages = catalog.of("package", project) if project else []
    position = value.get("$nth")
    wanted = [position] if isinstance(position, int) else []
    chosen = pick([entry.id for entry in packages], wanted)
    return chosen[0] if chosen else ordinal_question("package", state.language)


def known_fields(
    step: DraftStep, state: FillState, catalog: EntityCatalog
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Split the schema's parameters from unknown ones; plurals of task fields are renamed.

    A container id the step does not take is dropped only when it repeats the page's own
    object (it changes nothing); anything else is returned as unknown for a question.
    """
    model = PARAMETER_TYPES.get(step.action) or PARAMETER_MODELS.get(step.action)
    if model is None:
        return dict(step.params), {}
    fields = set(model.model_fields) | EDIT_KEYS.get(step.action, frozenset())
    params: dict[str, JsonValue] = {}
    unknown: dict[str, JsonValue] = {}
    for key, value in step.params.items():
        name = key
        if key not in fields and key in TASK_PLURALS and TASK_PLURALS[key] in fields:
            name = TASK_PLURALS[key]
        if name in fields:
            params.setdefault(name, value)
        elif key in CONTAINERS and (value is None or value == context_value(key, state, catalog)):
            continue
        else:
            unknown[key] = value
    return params, unknown


def _label_names(labels: JsonValue) -> list[str]:
    spoken: list[str] = []
    for item in labels if isinstance(labels, list) else []:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip():
            spoken.append(name.strip())
    return spoken


def _prepared(step: DraftStep, params: dict[str, JsonValue], names: list[str], text: str) -> None:
    """Add a request id, name a project after its new label set, keep the words as reason."""
    if step.action == "draft_label_set" and "name" not in params:
        topic = params.get("topic")
        if isinstance(topic, str) and topic.strip():
            params["name"] = topic.strip()[:200]
    model = PARAMETER_TYPES.get(step.action)
    fields = model.model_fields if model is not None else {}
    if "reason" in fields and "reason" not in params and text:
        # The audit trail then records why, in the person's own words.
        params["reason"] = text[:500]
    if "request_id" in fields:
        params.setdefault("request_id", new_id())
    if step.action == "create_label_set":
        spoken = _label_names(params.get("labels") or params.get("add_labels"))
        if not isinstance(params.get("name"), str) and "label_set_id" not in params and spoken:
            params["name"] = ", ".join(spoken)[:200]
        if isinstance(params.get("name"), str):
            names.append(str(params["name"]))
    if step.action == "create_project" and "name" not in params and names:
        params["name"] = names[-1]


def _selector_value(
    db: Database,
    field: str,
    value: dict[str, JsonValue],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
) -> JsonValue | Clarification:
    """Resolve a $tasks, $nth or $files selector; {"$empty": sentence} means nothing matches."""
    if "$tasks" in value:
        raw = value["$tasks"]
        found = _tasks(db, raw if isinstance(raw, dict) else {}, state, catalog)
        if isinstance(found, Clarification):
            return found
        if not found:
            holder = raw.get("holder") if isinstance(raw, dict) else None
            return {"$empty": nothing_to_change("tasks", str(holder or ""), state.language)}
        identifiers: list[JsonValue] = list(found)
        return identifiers if field.endswith("_ids") else {"$each": identifiers}
    if "$nth" in value:
        return _nth_package(value, state, catalog)
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
    return selection if selection is not None else _ask(field, current, [], state.language)


def _fill_value(
    db: Database,
    field: str,
    value: JsonValue,
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
) -> JsonValue | Clarification:
    """Resolve one value: selectors, single identities and lists of identities."""
    if isinstance(value, dict) and (
        "$tasks" in value or "$files" in value or ("$nth" in value and field == "package_id")
    ):
        return _selector_value(db, field, value, current, state, catalog)
    if field in FIELD_KINDS and isinstance(value, str):
        return _resolve_identity(field, value, current, state, catalog)
    if field in LIST_KINDS and isinstance(value, list):
        return _resolve_list(field, value, current, state, catalog)
    return value


def fill_steps(
    db: Database, steps: list[DraftStep], state: FillState, catalog: EntityCatalog
) -> FillResult:
    """Resolve every identity and selector; stop at the first question."""
    filled: list[DraftStep] = []
    names: list[str] = []
    for step in steps:
        params, unknown = known_fields(step, state, catalog)
        if unknown:
            question = unknown_question(step.action, list(unknown), state.language)
            return FillResult(clarification=Clarification(question=question, action=step.action))
        _prepared(step, params, names, state.text)
        current = step.model_copy(update={"params": params})
        for field in list(params):
            resolved = _fill_value(db, field, params[field], current, state, catalog)
            if isinstance(resolved, Clarification):
                return FillResult(clarification=resolved)
            if isinstance(resolved, dict) and set(resolved) == {"$empty"}:
                return FillResult(empty_selection=str(resolved["$empty"]))
            params[field] = resolved
        if step.action == "create_label_set":
            params = prepare_label_edit(db, params)
        filled.append(current.model_copy(update={"params": params}))
    return FillResult(steps=filled)


def _selection_defaults(
    params: dict[str, JsonValue], required: set[str], context: PageContext
) -> None:
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


def fill_defaults(
    step: DraftStep, required: set[str], state: FillState, catalog: EntityCatalog
) -> DraftStep:
    """Add page or previous-turn values for missing container identities.

    Only a read may also fall back to the single existing object; a write asks instead.
    """
    params = dict(step.params)
    single = step.action in PARAMETER_MODELS
    for field in CONTAINERS:
        if field in params or field not in required:
            continue
        value = _default_container(field, params, state, catalog, single=single)
        if value is not None:
            params[field] = value
    _selection_defaults(params, required, state.context)
    return step.model_copy(update={"params": params})
