# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic team skill dispatch: qualify by level, then least load, then person identity."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import AssignTasksParams
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.production_models import Assignment, AssignmentStage, Project, SkillRequirement
from datakeel.core.production_team_models import DispatchSkip
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.identity_rows import UserRow
from datakeel.storage.production_assignments import active_assignment, create_assignment
from datakeel.storage.production_dispatch_rules import active_loads, load_limit, qualifies
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
    session: Session, params: AssignTasksParams
) -> tuple[Project, SkillRequirement, list[ProductionTaskRow]]:
    if len(set(params.task_ids)) != len(params.task_ids):
        message = "Task assignment identities must be distinct"
        raise ValidationError(message)
    tasks = [require_task(session, identifier) for identifier in sorted(params.task_ids)]
    if len({task.project_id for task in tasks}) != 1:
        message = "One assignment operation must belong to a single project"
        raise ValidationError(message)
    project = require_mutable_project(session, tasks[0].project_id)
    if project.workflow_tier != "team":
        message = "Skill dispatch is available only in team-tier projects"
        raise ValidationError(message)
    requirement = params.skill_requirement or project.skill_requirement
    if requirement is None:
        message = "Skill dispatch requires a skill requirement on the request or the project"
        raise ValidationError(message)
    return project, requirement, sorted(tasks, key=lambda task: (-task.priority, task.id))


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


def dispatch_by_skill(
    session: Session, params: AssignTasksParams
) -> tuple[tuple[Assignment, ...], tuple[DispatchSkip, ...]]:
    """Assign each task to the least-loaded qualified person; ties go to the smallest identity.

    Tasks are taken in priority order (highest first) and then by identity. Each assignment
    raises that person's load before the next task is matched, so a batch stays reproducible.
    """
    project, requirement, tasks = _dispatch_context(session, params)
    candidates = params.candidates or tuple(session.scalars(select(UserRow.id)))
    pool = qualified_pool(session, project, requirement, params.stage, candidates)
    loads = dict.fromkeys(pool, 0) | active_loads(session, project.id, params.stage, pool)
    limit = load_limit(project, params.max_active_tasks)
    assigned: list[Assignment] = []
    skipped: list[DispatchSkip] = []
    for task in tasks:
        reason = _skip_reason(session, task, params.stage)
        eligible = _eligible(session, task, params.stage, pool) if reason is None else []
        available = [actor for actor in eligible if limit is None or loads[actor] < limit]
        if reason is None and not available:
            reason = "load_limit_reached" if eligible else "no_qualified_person"
        if reason is not None:
            skipped.append(DispatchSkip(task_id=task.id, reason=reason))
            continue
        chosen = min(available, key=lambda actor: (loads[actor], actor))
        assigned.append(create_assignment(session, task, chosen, params.stage, "skill"))
        loads[chosen] += 1
    if not assigned:
        message = "No task could be dispatched: " + ", ".join(
            sorted({item.reason for item in skipped})
        )
        raise ConflictError(message)
    return tuple(assigned), tuple(skipped)
