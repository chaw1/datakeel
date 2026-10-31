# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve group selectors ($tasks, $nth, $files) with read-only queries before planning.

The model describes a group; this module reads it from the project or dataset, so the plan
lists exactly the objects a confirmation changes and the card can say what was left out.
"""

from collections import Counter

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification, PageContext
from datakeel.intents import selectors
from datakeel.intents.catalog import SELF_WORDS, EntityCatalog, candidates
from datakeel.intents.drafts import DraftStep
from datakeel.intents.exclusions import excluded_text, include_question
from datakeel.intents.fill_state import (
    FillState,
    ask,
    context_value,
    in_scope,
    named_in_words,
    project_in_scope,
)
from datakeel.intents.segments import freed_snapshots, later_segment, once
from datakeel.intents.selectors import file_selection, named_files, ordinal_question, pick
from datakeel.intents.singular import says_one, which_task
from datakeel.intents.step_values import page_package
from datakeel.intents.task_scope import (
    CONDITIONS,
    SELECTOR_KEYS,
    Holder,
    from_end,
    is_nobody,
    place_number,
    select_tasks,
    task_number,
)
from datakeel.intents.verify import says_whole
from datakeel.intents.wording import nothing_to_change, whole_tasks_question
from datakeel.storage.database import Database
from datakeel.storage.identity_store import list_users
from datakeel.storage.intent_reads import TaskSnapshot, held_projects, task_snapshots

TASK_FIELDS = frozenset({"task_id", "task_ids"})
# One's own work: with no task named or on the page, the task is the speaker's own.
SELF_WORK = frozenset({"release_task", "submit_task", "heartbeat"})
# Reads that take a task group: "my task" there is any task the person holds or annotated.
TASK_READS = frozenset({"get_task", "lease_status", "production_objects"})
# Giving back or keeping one's own task with no stage said finds a hold in either stage.
ANY_STAGE = frozenset({"release_task", "heartbeat"})
# Conditions that count within one project's list, so they never span projects.
ORDERED = ("numbers", "positions", "first", "last", "package")


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


def _project(spec: dict[str, JsonValue], state: FillState, catalog: EntityCatalog) -> str | None:
    """The selector's project: as written in it, named in the words, else the page's.

    A package named without its project (a package name only one project has) also fixes
    the project. None means the project is unclear and has to be asked about.
    """
    written = spec.get("project_id", spec.get("project"))
    named = named_in_words("project_id", state, catalog)
    page = context_value("project_id", state, catalog)
    if isinstance(written, str) and written.strip():
        exact = catalog.get("project", written)
        found = [exact] if exact is not None else catalog.match("project", written)
        if len(found) != 1:
            return None
        project: str | None = found[0].id
        if project == page and named is not None:
            # The model copied the page's project although the person named another one.
            project = named
    else:
        project = project_in_scope(None, state, catalog)
    package = spec.get("package")
    if isinstance(package, str) and task_number(package) is None:
        owners = {entry.parent for entry in catalog.match("package", package)}
        if (project is None or project not in owners) and len(owners) == 1:
            return owners.pop()
    return project


def nth_package(
    value: JsonValue, project: str | None, state: FillState, catalog: EntityCatalog
) -> str | Clarification:
    """A package by its place in the list (2 or {"$nth": 2}) or by its name."""
    packages = catalog.of("package", project) if project else []
    position = value.get("$nth") if isinstance(value, dict) else value
    named = isinstance(position, str) and task_number(position) is None
    found = catalog.match("package", str(position), project) if named else []
    if len(found) == 1:
        return found[0].id
    # Not one package's name: a place in words ("第 3 个包", "the third package").
    number = place_number(position) if isinstance(position, (int, str)) else None
    if named and number is None:
        step = DraftStep(id="selector", action="assign_tasks")
        return ask("package_id", step, candidates(found or packages), state.language, str(position))
    if project is None and number:
        # No project yet: the Nth package of every project that has one is a candidate.
        places = [catalog.of("package", entry.id) for entry in catalog.of("project")]
        found = [listed[number - 1] for listed in places if len(listed) >= number]
        if len(found) == 1:
            return found[0].id
        step = DraftStep(id="selector", action="assign_tasks")
        return (
            ask("package_id", step, candidates(found), state.language)
            if found
            else (ordinal_question("package", state.language))
        )
    chosen = pick([entry.id for entry in packages], [number] if number else [])
    return chosen[0] if chosen else ordinal_question("package", state.language)


def _tasks(
    db: Database,
    spec: dict[str, JsonValue],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
    *,
    fan_out: bool = False,
) -> tuple[list[str], dict[str, int]] | Clarification:
    where = _where(db, spec, state, catalog)
    if isinstance(where, Clarification):
        return where
    if isinstance(where, list):
        spans = fan_out and len(where) > 1 and not any(key in spec for key in ORDERED)
        return (
            _across(db, where, spec, current, state, catalog)
            if spans
            else _choose_project(where, current, state, catalog)
        )
    project, holder = where
    stage = _stage(current)
    # Assigning for review only takes tasks waiting for review, so the stage is the condition.
    described = stage == "review" or any(key in spec for key in (*CONDITIONS, *ORDERED))
    if not described and not says_whole(state.text):
        # A bare "the tasks" is never widened to every task in the project.
        return Clarification(
            question=whole_tasks_question(state.language),
            action=current.action,
            fields=["$tasks.numbers"],
        )
    package = page_package(db, spec.get("package"), state) or (
        nth_package(spec["package"], project, state, catalog) if "package" in spec else None
    )
    if isinstance(package, Clarification):
        return package
    spec = from_end(spec, state.text)
    if current.action == "revoke_assignment" and holder is not None and says_whole(state.text):
        # "Mia 手上的都收回" asks for every one of her tasks, saved work included.
        said = spec.get("include")
        listed: list[JsonValue] = said if isinstance(said, list) else [str(said or "")]
        spec = {**spec, "include": [*listed, "annotated"]}
    snapshots = freed_snapshots(task_snapshots(db, project), state)
    snapshots = later_segment(spec, snapshots, state, current.action)  # "接下来两条"
    return _in_stages(snapshots, spec, current, state, (holder, package))


def _in_stages(
    snapshots: list[TaskSnapshot],
    spec: dict[str, JsonValue],
    current: DraftStep,
    state: FillState,
    found: tuple[Holder, str | None],
) -> tuple[list[str], dict[str, int]] | Clarification:
    """Select in the step's stage; a give-back with no stage said looks in both."""
    stage = _stage(current)
    either = not current.params.get("stage") and current.action in ANY_STAGE
    ids: list[str] = []
    excluded: Counter[str] = Counter()
    held: set[str] = set()
    for each in ("annotation", "review") if either else (stage,):
        scope = select_tasks(
            snapshots,
            spec,
            action=current.action,
            speaker=state.actor,
            found=found,
            stage=each,
        )
        if scope.missing:
            return ordinal_question("task", state.language)
        ids += [task for task in scope.ids if task not in ids]
        excluded.update(scope.excluded)
        held |= {each} if scope.ids else set()
    if either and len(held) == 1:
        # The one stage the holds were found in is the stage the step gives back or keeps.
        current.params["stage"] = held.pop()
    return ids, dict(excluded)


def _stage(current: DraftStep) -> str:
    """The stage a selector looks at: the step's own, review for a review, any for a read."""
    explicit = current.params.get("stage")
    stage = explicit if isinstance(explicit, str) and explicit else "annotation"
    stage = "review" if current.action == "review_task" else stage
    # A read about someone's task finds what they annotated, whatever its state.
    return "read" if current.action in TASK_READS else stage


def own_task(action: str, params: dict[str, JsonValue], context: PageContext) -> None:
    """Giving back, handing in or keeping "my task" with none named: the speaker's own."""
    paged = context.task_id or (context.selected_kind == "production_task" and context.selected_ids)
    if action in SELF_WORK and "task_id" not in params and not paged:
        params["task_id"] = {"$tasks": {"holder": "me"}}


def _where(
    db: Database, spec: dict[str, JsonValue], state: FillState, catalog: EntityCatalog
) -> tuple[str, Holder] | list[str] | Clarification:
    """(project, holder) of a selector, or the projects to choose from when none is said.

    Someone's tasks with no project said: the projects where that person holds work now.
    A team named as the holder means its members.
    """
    person = _holder(spec, state, catalog)
    team = _members(db, spec.get("holder"), catalog) if isinstance(person, Clarification) else None
    if isinstance(person, Clarification) and team is None:
        return person
    holder: Holder = team if team is not None else person if isinstance(person, str) else None
    project = _project(spec, state, catalog)
    if project is not None:
        return project, holder
    held = held_projects(db, holder) if isinstance(holder, str) else []
    return (held[0], holder) if len(held) == 1 else held


def _members(db: Database, raw: JsonValue, catalog: EntityCatalog) -> frozenset[str] | None:
    """The people of the one team the holder words name, or None."""
    teams = catalog.match("team", raw) if isinstance(raw, str) else []
    if len(teams) != 1:
        return None
    return frozenset(user.id for user in list_users(db) if teams[0].id in user.team_ids)


def _choose_project(
    held: list[str], current: DraftStep, state: FillState, catalog: EntityCatalog
) -> Clarification:
    """Ask for the project, offering the ones where the holder works (else all)."""
    offered = [entry for entry in catalog.of("project") if entry.id in held]
    step = DraftStep(id="selector", action=current.action)
    asked = ask("project_id", step, candidates(offered or catalog.of("project")), state.language)
    return asked.model_copy(update={"fields": ["$tasks.project_id"]})


def _across(
    db: Database,
    projects: list[str],
    spec: dict[str, JsonValue],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
) -> tuple[list[str], dict[str, int]] | Clarification:
    """One holder's described tasks in every project where they hold work."""
    ids: list[str] = []
    excluded: Counter[str] = Counter()
    for project in projects:
        found = _tasks(db, {**spec, "project_id": project}, current, state, catalog)
        if isinstance(found, Clarification):
            return found
        ids += found[0]
        excluded.update(found[1])
    return ids, dict(excluded)


def numbered(field: str, value: JsonValue) -> dict[str, JsonValue] | None:
    """Task numbers written as task ids ("#8", "第 8 个") become a numbers selector.

    A selector the model wrapped in a list (``[{"$tasks": {...}}]``) is the selector itself,
    and a dict of only group conditions is a group whose ``$tasks`` wrapper was left out.
    """
    if field not in TASK_FIELDS:
        return None
    if isinstance(value, dict) and value and set(value) <= SELECTOR_KEYS:
        return {"$tasks": value}
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        inner = value[0]
        return inner if "$tasks" in inner else None
    values = value if isinstance(value, list) else [value]
    found = [task_number(item) for item in values if isinstance(item, str)]
    if not values or len(found) != len(values) or None in found:
        return None
    listed: list[JsonValue] = [number for number in found if number is not None]
    return {"$tasks": {"numbers": listed}}


def _task_slot(
    db: Database,
    slot: tuple[str, dict[str, JsonValue]],
    current: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
    excluded: Counter[str],
) -> JsonValue | Clarification:
    field, value = slot
    raw = value["$tasks"]
    spec = raw if isinstance(raw, dict) else {}
    # A step that runs once per task may span projects; one list of tasks may not.
    wide = not field.endswith("_ids")
    found = once(
        spec, state, current.action, lambda: _tasks(db, spec, current, state, catalog, fan_out=wide)
    )
    if isinstance(found, Clarification):
        return found
    ids, left_out = found
    excluded.update(left_out)
    if not ids:
        holder = spec.get("holder")
        named = "" if is_nobody(holder, {}) else str(holder or "")
        if named.strip().casefold() in SELF_WORDS:
            named = "你" if state.language == "zh" else "you"
        if set(left_out) == {"closed"}:
            return {"$empty": excluded_text(left_out, state.language).strip()}
        if left_out:
            return include_question(left_out, named, current.action, state.language)
        return {"$empty": nothing_to_change("tasks", named, state.language)}
    if len(ids) > 1 and field == "task_id" and says_one(state.text):
        return which_task(db, ids, catalog, current.action, state.language)
    identifiers: list[JsonValue] = list(ids)
    return identifiers if field.endswith("_ids") else {"$each": identifiers}


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
        return _task_slot(db, slot, current, state, catalog, excluded)
    if "$nth" in value:
        return nth_package(value, _project({}, state, catalog), state, catalog)
    spec = value["$files"]
    # The dataset the selection or the words name wins over the page's.
    dataset = in_scope("dataset_id", value.get("dataset_id"), state, catalog)
    if dataset is None and isinstance(spec, dict):
        dataset = _holding_dataset(db, spec, catalog)
    paged = dataset == context_value("dataset_id", state, catalog)
    selection = file_selection(
        db,
        spec if isinstance(spec, dict) else {},
        dataset,
        state.context.version_id if paged else None,
        list(state.context.selected_ids) if paged else [],
    )
    if selection is not None and selection.get("$empty"):
        pending = selection.get("$pending") and selectors.still_computing(state.language)
        return {"$empty": pending or nothing_to_change("files", "", state.language)}
    return selection if selection is not None else ask(field, current, [], state.language)


def _holding_dataset(
    db: Database, spec: dict[str, JsonValue], catalog: EntityCatalog
) -> str | None:
    """Files named with no dataset said: the one dataset that has every one of them."""
    raw = spec.get("names")
    names = [item for item in raw if isinstance(item, str)] if isinstance(raw, list) else []
    if spec.get("kind") != "named" or not names:
        return None
    holding = [
        entry.id
        for entry in catalog.of("dataset")
        if named_files(db, entry.id, None, names) is not None
    ]
    return holding[0] if len(holding) == 1 else None
