# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic team skill dispatch: qualify by level, then least load, then person identity."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import AssignTasksParams
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.production_models import Assignment, AssignmentStage, Project, SkillRequirement
from datakeel.core.production_team_models import DispatchSkip
from datakeel.core.workbench_models import (
    DispatchLoad,
    DispatchPick,
    SkillDispatchPreview,
    SkillDispatchPreviewRequest,
)
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.identity_rows import UserRow
from datakeel.storage.production_assignments import active_assignment, create_assignment
from datakeel.storage.production_dispatch_rules import (
    active_loads,
    held_loads,
    load_limit,
    qualifies,
)
from datakeel.storage.production_load_locks import lock_people
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_separation import annotators
from datakeel.storage.production_tasks import require_mutable_project, require_task

_STAGE_SCOPE = {"annotation": "production:annotate", "review": "production:review"}
_STAGE_STATE = {"annotation": "pending", "review": "submitted"}


def qualified_pool(
    session: Session,
    project: Project,
    requirement: SkillRequirement,
    stage: AssignmentStage,
    candidates: Iterable[str],
) -> tuple[str, ...]:
    """Keep active registered people with stage authority and a sufficient skill level."""
    pool: list[str] = []
    for actor in sorted(set(candidates)):
        scopes = effective_scopes(session, actor, project.id).scopes
        if "*" not in scopes and _STAGE_SCOPE[stage] not in scopes:
            continue
        if qualifies(session, actor, requirement):
            pool.append(actor)
    return tuple(pool)


def _dispatch_context(
    session: Session,
    task_ids: tuple[str, ...],
    override: SkillRequirement | None,
    *,
    lock: bool = True,
) -> tuple[Project, SkillRequirement, list[ProductionTaskRow]]:
    if len(set(task_ids)) != len(task_ids):
        message = "Task assignment identities must be distinct"
        raise ValidationError(message)
    tasks = [
        require_task(session, identifier) if lock else _read_task(session, identifier)
        for identifier in sorted(task_ids)
    ]
    if len({task.project_id for task in tasks}) != 1:
        message = "One assignment operation must belong to a single project"
        raise ValidationError(message)
    project = require_mutable_project(session, tasks[0].project_id)
    if project.workflow_tier != "team":
        message = "Skill dispatch is available only in team-tier projects"
        raise ValidationError(message)
    requirement = override or project.skill_requirement
    if requirement is None:
        message = "Skill dispatch requires a skill requirement on the request or the project"
        raise ValidationError(message)
    return project, requirement, sorted(tasks, key=lambda task: (-task.priority, task.id))


def _read_task(session: Session, task_id: str) -> ProductionTaskRow:
    row = session.get(ProductionTaskRow, task_id)
    if row is None:
        message = "Production task was not found"
        raise NotFoundError(message)
    return row


def _eligible(
    session: Session, task: ProductionTaskRow, stage: AssignmentStage, pool: tuple[str, ...]
) -> list[str]:
    if stage == "annotation":
        if task.round > 0 and task.annotator_id is not None:
            return [actor for actor in pool if actor == task.annotator_id]
        return list(pool)
    excluded = annotators(session, task)
    return [actor for actor in pool if actor not in excluded]


def _skip_reason(session: Session, task: ProductionTaskRow, stage: AssignmentStage) -> str | None:
    if task.state != _STAGE_STATE[stage]:
        return "task_state_not_dispatchable"
    if active_assignment(session, task.id, stage) is not None:
        return "already_assigned"
    return None


def _match(
    session: Session,
    tasks: list[ProductionTaskRow],
    stage: AssignmentStage,
    pool: tuple[str, ...],
    loads: dict[str, int],
    limit: int | None,
) -> tuple[list[tuple[ProductionTaskRow, str]], list[DispatchSkip]]:
    picks: list[tuple[ProductionTaskRow, str]] = []
    skipped: list[DispatchSkip] = []
    for task in tasks:
        reason = _skip_reason(session, task, stage)
        eligible = _eligible(session, task, stage, pool) if reason is None else []
        available = [actor for actor in eligible if limit is None or loads[actor] < limit]
        if reason is None and not available:
            reason = "load_limit_reached" if eligible else "no_qualified_person"
        if reason is not None:
            skipped.append(DispatchSkip(task_id=task.id, reason=reason))
            continue
        chosen = min(available, key=lambda actor: (loads[actor], actor))
        picks.append((task, chosen))
        loads[chosen] += 1
    return picks, skipped


def dispatch_by_skill(
    session: Session, params: AssignTasksParams
) -> tuple[tuple[Assignment, ...], tuple[DispatchSkip, ...]]:
    """Assign each task to the least-loaded qualified person; ties go to the smallest identity.

    Tasks are taken in priority order (highest first) and then by identity. Each assignment
    raises that person's load before the next task is matched, so a batch stays reproducible.
    """
    project, requirement, tasks = _dispatch_context(
        session, params.task_ids, params.skill_requirement
    )
    candidates = params.candidates or tuple(session.scalars(select(UserRow.id)))
    pool = qualified_pool(session, project, requirement, params.stage, candidates)
    lock_people(session, project.id, pool)
    loads = dict.fromkeys(pool, 0) | held_loads(session, project.id, params.stage, pool)
    limit = load_limit(project, params.max_active_tasks)
    picks, skipped = _match(session, tasks, params.stage, pool, loads, limit)
    if not picks:
        message = "No task could be dispatched: " + ", ".join(
            sorted({item.reason for item in skipped})
        )
        raise ConflictError(message)
    assigned = tuple(
        create_assignment(session, task, actor, params.stage, "skill") for task, actor in picks
    )
    return assigned, tuple(skipped)


def preview_skill_dispatch(
    session: Session, project_id: str, request: SkillDispatchPreviewRequest
) -> SkillDispatchPreview:
    """Compute what a skill dispatch would do now, with the same rules and no locks or writes."""
    project, requirement, tasks = _dispatch_context(
        session, request.task_ids, request.skill_requirement, lock=False
    )
    if project.id != project_id:
        message = "Dispatch tasks must belong to the selected project"
        raise ValidationError(message)
    candidates = request.candidates or tuple(session.scalars(select(UserRow.id)))
    pool = qualified_pool(session, project, requirement, request.stage, candidates)
    current = dict.fromkeys(pool, 0) | active_loads(session, project.id, request.stage, pool)
    limit = load_limit(project, request.max_active_tasks)
    picks, skipped = _match(session, tasks, request.stage, pool, dict(current), limit)
    added = {actor: sum(1 for _, chosen in picks if chosen == actor) for actor in pool}
    return SkillDispatchPreview(
        project_id=project.id,
        stage=request.stage,
        skill_requirement=requirement,
        max_active_tasks=limit,
        qualified=pool,
        picks=tuple(DispatchPick(task_id=task.id, actor=actor) for task, actor in picks),
        people=tuple(
            DispatchLoad(actor=actor, current=current[actor], added=added[actor]) for actor in pool
        ),
        unassigned=tuple(skipped),
    )
