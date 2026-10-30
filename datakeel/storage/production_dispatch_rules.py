# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team-tier skill levels, open load and per-person load limits shared by all dispatch paths."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.identity_models import Skill, User
from datakeel.core.production_models import AssignmentStage, Project, SkillRequirement
from datakeel.storage.identity_rows import SkillRow, UserRow
from datakeel.storage.production_leases import LEASED_STATES
from datakeel.storage.production_load_locks import lock_people, require_people_locked
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow


def skill_level(session: Session, actor: str, requirement: SkillRequirement) -> int:
    """Return an active user's best active skill level for the required type and domain, or 0."""
    row = session.get(UserRow, actor)
    if row is None:
        return 0
    user = User.model_validate(row.payload)
    if user.status != "active":
        return 0
    levels = [0]
    for identifier in user.skill_ids:
        skill_row = session.get(SkillRow, identifier)
        if skill_row is None:
            continue
        skill = Skill.model_validate(skill_row.payload)
        if (
            skill.status == "active"
            and skill.annotation_type == requirement.annotation_type
            and skill.domain == requirement.domain
        ):
            levels.append(skill.level)
    return max(levels)


def qualifies(session: Session, actor: str, requirement: SkillRequirement) -> bool:
    """Admit only people whose matching skill level reaches the required minimum."""
    return skill_level(session, actor, requirement) >= requirement.min_level


def active_loads(
    session: Session,
    project_id: str,
    stage: AssignmentStage,
    actors: Iterable[str] | None = None,
) -> dict[str, int]:
    """Count each person's open work of one stage within the project: the one load figure.

    Open work is an effective assignment whose stage is still running: annotation that is
    pending (including returned rework) or in progress, and review that is in progress.
    An annotation assignment kept while its task waits for review, or after approval, is
    not open. Claims, named and skill dispatch, the assignee picker and ``skill_workload``
    all count this way.
    """
    statement = (
        select(ProductionAssignmentRow.actor, func.count())
        .join(ProductionTaskRow, ProductionTaskRow.id == ProductionAssignmentRow.task_id)
        .where(
            ProductionTaskRow.project_id == project_id,
            ProductionAssignmentRow.stage == stage,
            ProductionAssignmentRow.active.is_(True),
            ProductionTaskRow.state.in_(LEASED_STATES[stage]),
        )
        .group_by(ProductionAssignmentRow.actor)
    )
    if actors is not None:
        statement = statement.where(ProductionAssignmentRow.actor.in_(list(actors)))
    return {actor: int(count) for actor, count in session.execute(statement).all()}


def held_loads(
    session: Session, project_id: str, stage: AssignmentStage, actors: Iterable[str]
) -> dict[str, int]:
    """Count loads for a limit decision; each person's load lock must already be held."""
    people = tuple(actors)
    require_people_locked(session, project_id, people)
    return active_loads(session, project_id, stage, people)


def require_dispatch_limit(project: Project, override: int | None) -> None:
    """Let one dispatch lower the project's per-person limit, never raise it."""
    setting = project.max_active_tasks
    if override is not None and setting is not None and override > setting:
        message = (
            f"max_active_tasks {override} for this dispatch is above the project setting of "
            f"{setting}; a dispatch may use {setting} or a lower limit"
        )
        raise ValidationError(message)


def load_limit(project: Project, override: int | None = None) -> int | None:
    """Apply a per-person limit only in the team tier; a request may only lower the limit."""
    require_dispatch_limit(project, override)
    if project.workflow_tier != "team":
        return None
    return override if override is not None else project.max_active_tasks


def require_capacity(
    session: Session,
    project: Project,
    actor: str,
    stage: AssignmentStage,
    adding: int = 1,
    override: int | None = None,
) -> None:
    """Reject work that would take a person above the project's open-task limit."""
    limit = load_limit(project, override)
    if limit is None:
        return
    load = held_loads(session, project.id, stage, (actor,)).get(actor, 0)
    if load + adding > limit:
        message = (
            f"{actor} holds {load} active {stage} tasks; adding {adding} would exceed "
            f"the limit of {limit}"
        )
        raise ConflictError(message)


def require_claim_strategy(
    session: Session, project: Project, actor: str, stage: AssignmentStage
) -> None:
    """Apply the team dispatch strategy to self-claims of annotation work."""
    if project.workflow_tier != "team" or stage != "annotation":
        return
    if project.dispatch_strategy == "assign":
        message = "This team project dispatches by manager assignment; self-claim is disabled"
        raise ValidationError(message)
    requirement = project.skill_requirement
    if (
        project.dispatch_strategy == "skill"
        and requirement is not None
        and not qualifies(session, actor, requirement)
    ):
        message = (
            f"Claim requires skill {requirement.annotation_type}/{requirement.domain} "
            f"at level {requirement.min_level} or above"
        )
        raise AuthorizationError(message)
    lock_people(session, project.id, (actor,))
    require_capacity(session, project, actor, stage)
