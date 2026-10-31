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
from dataclasses import dataclass

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.core.production_models import Project
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import task_holders
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
    if any(task.id not in holders for task in tasks):
        return None
    return (
        ("nothing_free_package", {}) if target.package else ("nothing_free", {"name": project.name})
    )


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
    "claim_task": ("finalized", "free_task"),
    **dict.fromkeys(
        (
            "assign_tasks",
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

REASONS: dict[str, tuple[str, str]] = {
    "finalized": (
        "「{name}」已经定稿, 不能再改; 要接着做得新建一个项目",
        '"{name}" is finalized and cannot change; start a new project to go on',
    ),
    "not_approved": (
        "「{name}」还有 {count} 条任务没通过审核, 现在不能定稿; 可以先把这些任务审完",
        (
            '"{name}" still has {count} tasks not approved, so it cannot be finalized yet; '
            "review them first"
        ),
    ),
    "not_accepted": (
        "「{name}」还有 {count} 个任务包没验收, 团队档要每个包都验收后才能定稿; 可以先验收这些包",
        (
            '"{name}" has {count} packages not accepted yet; a team project finalizes only after '
            "every package is accepted, so accept them first"
        ),
    ),
    "not_team": (
        "只有团队档项目才按包验收, 「{name}」不是团队档",
        'only team projects accept work package by package, and "{name}" is not one',
    ),
    "package_not_approved": (
        "这个任务包里还有 {count} 条任务没通过审核, 现在不能验收; 可以先把它们审完",
        (
            "{count} tasks in that package are not approved yet, so it cannot be accepted; "
            "review them first"
        ),
    ),
    "accepted": (
        "这个任务包已经验收通过了, 现在的状态就是已验收, 不用再验收",
        "That package is already accepted; its state is accepted, so nothing to do",
    ),
    "not_held": (
        "其中 {count} 条任务现在不在你手上, 只有领着任务的人才能保存或提交; 可以先领取或派给你",
        (
            "{count} of those tasks are not in your hands, and only the person holding a task can "
            "save or hand it in; claim it or have it assigned to you first"
        ),
    ),
    "not_saved": (
        (
            "其中 {count} 条任务没有可提交的标注 (还没保存过, 或已经提交了), 现在不能提交; "
            "先标注并保存"
        ),
        (
            "{count} of those tasks have nothing to hand in (nothing saved yet, or already handed "
            "in); annotate and save first"
        ),
    ),
    "not_releasable": (
        "其中 {count} 条任务不在进行中 (已经提交、通过或还没开始), 不能放弃",
        (
            "{count} of those tasks are not in progress (handed in, approved or not started), so "
            "they cannot be given up"
        ),
    ),
    "split": (
        "「{name}」已经切过包了, 不能再切",
        '"{name}" is already split into packages and cannot be split again',
    ),
    "not_revocable": (
        "其中 {count} 条任务已经提交或通过了, 不能收回; 要重做可以先重新打开",
        (
            "{count} of those tasks are already submitted or approved and cannot be taken back; "
            "reopen them instead"
        ),
    ),
    "no_lease": (
        "「{name}」是小组档, 领到的任务不限时, 没有领取时限要续",
        '"{name}" is a group project; claimed tasks are not timed, so there is no lease to renew',
    ),
    "nothing_free": (
        "「{name}」里现在没有可领的任务 (都已经有人在做, 或者已经交了)",
        'There is no task free to claim in "{name}" now (all are taken or handed in)',
    ),
    "nothing_free_package": (
        "这个任务包里现在没有可领的任务 (都已经有人在做, 或者已经交了)",
        "There is no task free to claim in that package now (all are taken or handed in)",
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
    return Target(
        project=project,
        tasks=_tasks(step),
        package=package if isinstance(package, str) else None,
        actor=actor,
        stage=stage if isinstance(stage, str) and stage else "annotation",
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
