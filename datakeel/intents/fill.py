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

from collections import Counter

from pydantic import Field, JsonValue

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.intent_models import Clarification
from datakeel.core.models import BoundaryModel, new_id
from datakeel.intents.catalog import (
    FIELD_KINDS,
    LIST_KINDS,
    SELF_WORDS,
    CatalogEntry,
    EntityCatalog,
    candidates,
)
from datakeel.intents.derived import model_record
from datakeel.intents.drafts import DraftStep
from datakeel.intents.duplicates import new_name_fields
from datakeel.intents.edits import prepare_label_edit
from datakeel.intents.fill_state import (
    FillState,
    ask,
    context_value,
    named_in_words,
    project_in_scope,
)
from datakeel.intents.grounding import grounded
from datakeel.intents.group_fill import numbered, selector_value
from datakeel.intents.object_edits import LIST_EDITS, new_object_field, prepare_user_edit
from datakeel.intents.selectors import page_selection
from datakeel.intents.signatures import near_value
from datakeel.intents.wording import (
    disabled_question,
    unknown_labels_question,
    unknown_question,
)
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.storage.database import Database

CONTAINERS = ("dataset_id", "version_id", "project_id", "package_id", "label_set_id")
SINGLE_DEFAULTS = frozenset({"dataset_id", "project_id"})
TASK_PLURALS = {"task_ids": "task_id", "task_id": "task_ids"}
# Intent-only spellings of an edit that is applied to what exists into the full list.
EDIT_KEYS = {
    "create_label_set": frozenset({"add_labels", "remove_labels", "rename_labels"}),
    "manage_users": frozenset(LIST_EDITS),
}
# Fields that hand work to a person: a disabled account cannot take it.
RECEIVERS = frozenset({"actor", "leader_id", "assignee"})
__all__ = [
    "FillResult",
    "FillState",
    "context_value",
    "fill_defaults",
    "fill_steps",
]


class FillResult(BoundaryModel):
    """Filled steps, or the first question that has to be answered before planning."""

    steps: list[DraftStep] = Field(default_factory=list[DraftStep])
    clarification: Clarification | None = None
    empty_selection: str | None = None
    empty_step: str | None = None
    excluded: dict[str, dict[str, int]] = Field(default_factory=dict[str, dict[str, int]])


def _default_container(
    field: str,
    params: dict[str, JsonValue],
    state: FillState,
    catalog: EntityCatalog,
    *,
    single: bool,
) -> str | None:
    package = params.get("package_id")
    owner = catalog.get("package", package) if isinstance(package, str) else None
    if field == "project_id" and owner is not None and owner.parent:
        return owner.parent  # a package belongs to exactly one project
    # A container the words name wins over the page; the page is only the default.
    value = named_in_words(field, state, catalog) or context_value(field, state, catalog)
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
    if kind == "package":
        parent = project_in_scope(step.params.get("project_id"), state, catalog)
    page = context_value(field, state, catalog) if field in CONTAINERS else None
    found = catalog.match(kind, value, parent) or (catalog.match(kind, value) if parent else [])
    found = _page_first(found, page)
    named = named_in_words(field, state, catalog) if field in CONTAINERS else None
    if named is not None and len(found) == 1 and found[0].id == page and named != page:
        # The model copied the page's object although the person named another one.
        found = [entry for entry in catalog.of(kind) if entry.id == named]
    said = step.said.get(field)
    only = step.action in PARAMETER_MODELS and len(catalog.of(kind, parent)) == 1
    if len(found) == 1 and (only or grounded(field, found[0], state.text, page, said)):
        if found[0].status != "active" and field in RECEIVERS:
            active = [entry for entry in catalog.of(kind) if entry.status == "active"]
            question = disabled_question(found[0].label, state.language)
            asked = ask(field, step, candidates(active), state.language)
            return asked.model_copy(update={"question": question})
        return found[0].id
    if len(found) == 1:
        # Named by nobody: the model copied it from the catalog, so ask instead of guessing.
        return ask(field, step, candidates(catalog.of(kind, parent)), state.language)
    pool = found or catalog.of(kind, parent)
    return ask(field, step, candidates(pool), state.language, said or value)


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
            return ask(field, step, candidates(found or catalog.of(kind)), state.language, value)
        resolved.append(found[0].id)
    return resolved


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


def _fill_value(
    db: Database,
    field: str,
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
    excluded: Counter[str],
) -> JsonValue | Clarification:
    """Resolve one value: selectors, single identities and lists of identities."""
    value = current.params[field]
    value = numbered(field, value) or value
    if isinstance(value, dict) and (
        "$tasks" in value
        or "$files" in value
        or ("$nth" in value and "$ref" not in value and field == "package_id")
    ):
        return selector_value(db, (field, value), current, state, catalog, excluded)
    if field in FIELD_KINDS and isinstance(value, str):
        return _resolve_identity(field, value, current, state, catalog)
    if field in LIST_KINDS and isinstance(value, list):
        return _resolve_list(field, value, current, state, catalog)
    return _selection_dataset(value, current, state, catalog) if field == "selection" else value


def _selection_dataset(
    value: JsonValue, current: DraftStep, state: FillState, catalog: EntityCatalog
) -> JsonValue | Clarification:
    """A selection's dataset written as its name ("叶片样本") is that dataset's identity."""
    dataset = value.get("dataset_id") if isinstance(value, dict) else None
    if not isinstance(value, dict) or not isinstance(dataset, str):
        return value
    if catalog.get("dataset", dataset) is not None:
        return value
    resolved = _resolve_identity("dataset_id", dataset, current, state, catalog)
    return resolved if isinstance(resolved, Clarification) else {**value, "dataset_id": resolved}


def fill_steps(
    db: Database, steps: list[DraftStep], state: FillState, catalog: EntityCatalog
) -> FillResult:
    """Resolve every identity and selector; stop at the first question."""
    filled: list[DraftStep] = []
    names: list[str] = []
    left_out: dict[str, dict[str, int]] = {}
    for drafted in steps:
        step = model_record(drafted)
        params, unknown = known_fields(step, state, catalog)
        params = {key: near_value(step.action, key, value) for key, value in params.items()}
        if unknown:
            question = unknown_question(step.action, unknown, state.language)
            return FillResult(clarification=Clarification(question=question, action=step.action))
        _prepared(step, params, names, state.text)
        fresh = new_object_field(step.action, params)
        current = step.model_copy(update={"params": params})
        excluded: Counter[str] = Counter()
        # New names are never looked up: the object they name does not exist yet.
        new = {fresh, *new_name_fields(step.action, params)}
        for field in [name for name in params if name not in new]:
            resolved = _fill_value(db, field, current, state, catalog, excluded)
            if isinstance(resolved, Clarification):
                return FillResult(clarification=resolved)
            if isinstance(resolved, dict) and set(resolved) == {"$empty"}:
                return FillResult(empty_selection=str(resolved["$empty"]), empty_step=step.id)
            params[field] = resolved
        if step.action == "create_label_set":
            edit = prepare_label_edit(db, params)
            if edit.unknown:
                question = unknown_labels_question(edit.unknown, edit.existing, state.language)
                return FillResult(
                    clarification=Clarification(question=question, action=step.action)
                )
            params = edit.params
        params = prepare_user_edit(db, params) if step.action == "manage_users" else params
        filled.append(current.model_copy(update={"params": params}))
        if excluded:
            left_out[step.id] = dict(excluded)
    return FillResult(steps=filled, excluded=left_out)


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
    page_selection(params, required, state.context)
    return step.model_copy(update={"params": params})
