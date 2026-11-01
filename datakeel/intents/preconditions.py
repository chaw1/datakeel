# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What each state-changing action needs of the current state, checked before a card.

Every registered production action declares its preconditions by name in ``NEEDS``; the
checks are shared and read only the current state. They mirror what execution refuses
(``storage/production_*.py``), so a plan that would fail after confirmation is answered
instead, with what is missing and what to do first. A check is skipped when an earlier step
of the same plan changes the state it reads ("先审完再定稿").
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.core.production_models import Project
from datakeel.intents.claim_effects import claim_effects
from datakeel.intents.precondition_reasons import REASONS
from datakeel.storage.database import Database
from datakeel.storage.identity_store import list_users
from datakeel.storage.intent_reads import newer_versions, open_load, own_work, task_holders
from datakeel.storage.production_acceptance import (
    acceptance_state,
    latest_inspection,
    package_tasks,
)
from datakeel.storage.production_leases import LEASED_STATES
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    list_packages,
    list_tasks,
    project_for_params,
)

EDITABLE = frozenset({"pending", "in_progress"})
RELEASABLE = {"annotation": "in_progress", "review": "in_review"}


@dataclass(frozen=True)
class Target:
    """The objects one step acts on, read once."""

    project: Project | None
    tasks: tuple[str, ...]
    package: str | None
    actor: str
    stage: str
    assignee: str | None = None
    limit: int | None = None
    load_delta: int = 0
    prior_claims: int = 0
    reserved_tasks: frozenset[str] = frozenset()


Found = tuple[str, dict[str, str]] | None
Check = Callable[[Database, Target], Found]


def _finalized(db: Database, target: Target) -> Found:
    del db
    project = target.project
    if project is None or project.finalized_version_id is None:
        return None
    return "finalized", {"name": project.name}


def _all_approved(db: Database, target: Target) -> Found:
    project = target.project
    if project is None:
        return None
    left = [task for task in list_tasks(db, project.id) if task.state != "approved"]
    return ("not_approved", {"name": project.name, "count": str(len(left))}) if left else None


def _packages_accepted(db: Database, target: Target) -> Found:
    project = target.project
    if project is None or project.workflow_tier != "team":
        return None
    pending = 0
    with db.session() as session:
        for package in list_packages(db, project.id):
            _, rows = package_tasks(session, package.id)
            latest, _ = latest_inspection(session, package.id)
            pending += acceptance_state(rows, latest) != "accepted"
    return ("not_accepted", {"name": project.name, "count": str(pending)}) if pending else None


def _team_only(db: Database, target: Target) -> Found:
    del db
    project = target.project
    if project is None or project.workflow_tier == "team":
        return None
    return "not_team", {"name": project.name}


def _package_approved(db: Database, target: Target) -> Found:
    if target.package is None:
        return None
    try:
        with db.session() as session:
            _, rows = package_tasks(session, target.package)
    except NotFoundError:
        return None
    left = sum(row.state != "approved" for row in rows)
    return ("package_not_approved", {"count": str(left)}) if left else None


def _package_open(db: Database, target: Target) -> Found:
    """A package accepted already: say so, with the state, instead of accepting it again."""
    if target.package is None:
        return None
    try:
        with db.session() as session:
            _, rows = package_tasks(session, target.package)
            latest, _ = latest_inspection(session, target.package)
    except NotFoundError:
        return None
    return ("accepted", {}) if acceptance_state(rows, latest) == "accepted" else None


def _held(db: Database, target: Target) -> Found:
    """Saving or handing in needs the task in the speaker's hands (group and team)."""
    project = target.project
    if not target.actor or project is None or project.workflow_tier == "personal":
        return None
    holders = task_holders(db, list(target.tasks), "annotation")
    away = [task for task in target.tasks if holders.get(task) != target.actor]
    return ("not_held", {"count": str(len(away))}) if away else None


def _saved_and_open(db: Database, target: Target) -> Found:
    try:
        tasks = [get_task(db, task) for task in target.tasks]
    except NotFoundError:
        return None
    late = [task for task in tasks if task.state not in EDITABLE or task.latest_revision_id is None]
    return ("not_saved", {"count": str(len(late))}) if late else None


def _releasable(db: Database, target: Target) -> Found:
    wanted = RELEASABLE.get(target.stage)
    try:
        tasks = [get_task(db, task) for task in target.tasks]
    except NotFoundError:
        return None
    late = [task for task in tasks if wanted is not None and task.state != wanted]
    return ("not_releasable", {"count": str(len(late))}) if late else None


def _not_split(db: Database, target: Target) -> Found:
    project = target.project
    if project is None or not list_packages(db, project.id):
        return None
    return "split", {"name": project.name}


def _revocable(db: Database, target: Target) -> Found:
    """Handed-in or approved work is not taken back; it is reopened instead."""
    states = LEASED_STATES.get(target.stage, ())
    try:
        tasks = [get_task(db, task) for task in target.tasks]
    except NotFoundError:
        return None
    late = [task for task in tasks if task.state not in states]
    return ("not_revocable", {"count": str(len(late))}) if late else None


def _leased(db: Database, target: Target) -> Found:
    """Only team projects time a claim, so only they have a lease to renew."""
    del db
    project = target.project
    if project is None or project.workflow_tier != "group":
        return None
    return "no_lease", {"name": project.name}


def _free_task(db: Database, target: Target) -> Found:
    """Claiming needs a task nobody holds in that stage (in the named package, if any)."""
    project = target.project
    if project is None or project.workflow_tier == "personal":
        return None
    expected = "pending" if target.stage == "annotation" else "submitted"
    tasks = [
        task
        for task in list_tasks(db, project.id)
        if task.state == expected
        and target.package in (None, task.package_id)
        and (target.stage != "annotation" or task.round == 0 or task.annotator_id == target.actor)
    ]
    holders = task_holders(db, [task.id for task in tasks], target.stage)
    free = [
        task for task in tasks if task.id not in holders and task.id not in target.reserved_tasks
    ]
    if project.workflow_tier == "team" and target.stage == "review":
        own = set(own_work(db, [task.id for task in free], target.actor))
        free = [task for task in free if task.id not in own]
        if not free and own:
            return "own_work", {"person": _name(db, target.actor), "count": str(len(own))}
    free = free[target.prior_claims :]
    if free:
        return None
    return (
        ("nothing_free_package", {}) if target.package else ("nothing_free", {"name": project.name})
    )


def _claim_strategy(db: Database, target: Target) -> Found:
    """Manager-assigned team annotation is dispatched, never claimed by the annotator."""
    del db
    project = target.project
    if (
        project is None
        or project.workflow_tier != "team"
        or target.stage != "annotation"
        or project.dispatch_strategy != "assign"
    ):
        return None
    return "assign_only", {"name": project.name}


def _name(db: Database, person: str) -> str:
    return next((user.display_name for user in list_users(db) if user.id == person), person)


def _capacity(db: Database, target: Target) -> Found:
    """A dispatch only lowers the per-person limit; in a team project the work must fit it."""
    project, person = target.project, target.assignee
    if project is None or not person:
        return None
    setting = project.max_active_tasks
    if target.limit is not None and setting is not None and target.limit > setting:
        return "above_limit", {"asked": str(target.limit), "limit": str(setting)}
    limit = target.limit if target.limit is not None else setting
    if project.workflow_tier != "team" or limit is None:
        return None
    stage = "review" if target.stage == "review" else "annotation"
    load = open_load(db, project.id, stage, person) + target.load_delta
    adding = max(len(target.tasks), 1)
    if load + adding <= limit:
        return None
    values = {"load": str(load), "adding": str(adding), "limit": str(limit)}
    return "over_limit", {"person": _name(db, person), **values}


def _separate(db: Database, target: Target) -> Found:
    """Team review never goes to anyone who annotated the task, in any round or handover."""
    project, person = target.project, target.assignee
    if project is None or project.workflow_tier != "team" or target.stage != "review":
        return None
    own = own_work(db, list(target.tasks), person) if person else []
    return (
        ("own_work", {"person": _name(db, person or ""), "count": str(len(own))}) if own else None
    )


def _upgradable(db: Database, target: Target) -> Found:
    """Upgrading needs a newer template revision or a newer published label-set version."""
    project = target.project
    if project is None or newer_versions(db, project):
        return None
    return "up_to_date", {"name": project.name}


@dataclass(frozen=True)
class Precondition:
    """One shared check and the actions earlier in a plan that can change what it reads."""

    check: Check
    changed_by: frozenset[str] = frozenset()


PRECONDITIONS: dict[str, Precondition] = {
    "finalized": Precondition(_finalized),
    "all_approved": Precondition(
        _all_approved, frozenset({"review_task", "submit_task", "accept_package"})
    ),
    "packages_accepted": Precondition(_packages_accepted, frozenset({"accept_package"})),
    "team_only": Precondition(_team_only, frozenset({"upgrade_project"})),
    "package_approved": Precondition(_package_approved, frozenset({"review_task", "submit_task"})),
    "package_open": Precondition(_package_open),
    "held": Precondition(_held, frozenset({"assign_tasks", "claim_task", "revoke_assignment"})),
    "saved_and_open": Precondition(_saved_and_open, frozenset({"save_revision", "reopen_task"})),
    "releasable": Precondition(_releasable, frozenset({"save_revision", "claim_task"})),
    "not_split": Precondition(_not_split),
    "revocable": Precondition(_revocable, frozenset({"reopen_task", "review_task"})),
    "leased": Precondition(_leased, frozenset({"upgrade_project"})),
    "free_task": Precondition(
        _free_task, frozenset({"revoke_assignment", "release_task", "reopen_task", "review_task"})
    ),
    "claim_strategy": Precondition(
        _claim_strategy, frozenset({"configure_project", "upgrade_project"})
    ),
    "capacity": Precondition(
        _capacity,
        frozenset({"configure_project", "upgrade_project", "revoke_assignment", "release_task"})
        | frozenset({"submit_task", "review_task"}),
    ),
    "separate": Precondition(_separate),
    "upgradable": Precondition(_upgradable, frozenset({"create_label_set", "publish_label_set"})),
}

# What each registered state-changing action needs; execution refuses the rest.
_TASK_WORK = ("finalized",)
NEEDS: dict[str, tuple[str, ...]] = {
    "finalize_project": ("finalized", "all_approved", "packages_accepted"),
    "accept_package": ("team_only", "finalized", "package_open", "package_approved"),
    "submit_task": ("finalized", "held", "saved_and_open"),
    "save_revision": ("finalized", "held"),
    "release_task": ("finalized", "releasable"),
    "split_packages": ("finalized", "not_split"),
    "revoke_assignment": ("finalized", "revocable"),
    "heartbeat": ("finalized", "leased"),
    "claim_task": ("finalized", "claim_strategy", "capacity", "free_task"),
    "assign_tasks": ("finalized", "capacity", "separate"),
    "upgrade_project_template": ("finalized", "upgradable"),
    **dict.fromkeys(
        (
            "reopen_task",
            "review_task",
            "configure_project",
            "upgrade_project",
            "run_prelabel",
            "import_predictions",
        ),
        _TASK_WORK,
    ),
}


def _concrete(step: ChainStep) -> dict[str, JsonValue]:
    params = {key: value for key, value in step.params.items() if not isinstance(value, dict)}
    return {**params, **(step.items[0] if step.items else {})}


def _tasks(step: ChainStep) -> tuple[str, ...]:
    found: list[str] = []
    for entry in [{**step.params, **item} for item in step.items] or [step.params]:
        for key in ("task_id", "task_ids"):
            value = entry.get(key)
            listed = value if isinstance(value, list) else [value]
            found += [item for item in listed if isinstance(item, str)]
    return tuple(dict.fromkeys(found))


def _target(db: Database, step: ChainStep, actor: str) -> Target:
    try:
        with db.session() as session:
            project_id = project_for_params(session, _concrete(step))
        project = get_project(db, project_id) if project_id else None
    except (NotFoundError, ValidationError):
        project = None
    package = step.params.get("package_id")
    stage = step.params.get("stage")
    assignee, limit = step.params.get("actor"), step.params.get("max_active_tasks")
    if step.action == "claim_task":
        assignee = actor
    return Target(
        project=project,
        tasks=_tasks(step),
        package=package if isinstance(package, str) else None,
        actor=actor,
        stage=stage if isinstance(stage, str) and stage else "annotation",
        assignee=assignee if isinstance(assignee, str) and assignee else None,
        limit=limit if isinstance(limit, int) and not isinstance(limit, bool) else None,
    )


def unmet(
    db: Database, step: ChainStep, actor: str, language: str, earlier: Sequence[ChainStep] = ()
) -> str | None:
    """What this step needs that the current state lacks, in words; None when all is met."""
    needs = NEEDS.get(step.action, ())
    if not needs:
        return None
    changed = {item.action for item in earlier}
    target = _target(db, step, actor)
    if step.action == "claim_task" and target.project is not None:
        effects = claim_effects(db, target.project, actor, target.stage, target.package, earlier)
        target = replace(target, **vars(effects))
        changed -= {"configure_project", "upgrade_project"}
    for name in needs:
        rule = PRECONDITIONS[name]
        if rule.changed_by & changed:
            continue
        found = rule.check(db, target)
        if found is not None:
            reason, values = found
            zh, en = REASONS[reason]
            return (zh if language == "zh" else en).format(**values)
    return None
