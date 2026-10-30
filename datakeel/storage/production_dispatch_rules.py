# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team-tier skill levels, current load and per-person load limits shared by all dispatch paths."""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.identity_models import Skill, User
from datakeel.core.production_models import AssignmentStage, Project, SkillRequirement
from datakeel.storage.identity_rows import SkillRow, UserRow
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
    """Count each person's effective assignments of one stage within the project."""
    statement = (
        select(ProductionAssignmentRow.actor, func.count())
        .join(ProductionTaskRow, ProductionTaskRow.id == ProductionAssignmentRow.task_id)
        .where(
            ProductionTaskRow.project_id == project_id,
            ProductionAssignmentRow.stage == stage,
            ProductionAssignmentRow.active.is_(True),
        )
        .group_by(ProductionAssignmentRow.actor)
    )
    if actors is not None:
        statement = statement.where(ProductionAssignmentRow.actor.in_(list(actors)))
    return {actor: int(count) for actor, count in session.execute(statement).all()}


def load_limit(project: Project, override: int | None = None) -> int | None:
    """Apply a per-person limit only in the team tier; a request may set its own limit."""
    if project.workflow_tier != "team":
        return None
    return override if override is not None else project.max_active_tasks


def require_capacity(
    session: Session,
    project: Project,
    actor: str,
    stage: AssignmentStage,
    adding: int = 1,
) -> None:
    """Reject work that would take a person above the project's active-task limit."""
    limit = load_limit(project)
    if limit is None:
        return
    load = active_loads(session, project.id, stage, (actor,)).get(actor, 0)
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
    require_capacity(session, project, actor, stage)
