# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional user, team, role-binding and skill maintenance."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.actions.identity_parameters import ManageSkillsParams, ManageUsersParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.identity_models import Skill, Team, User
from datakeel.core.models import AssetRef
from datakeel.storage.identity_authorization import require_binding_authority
from datakeel.storage.identity_rows import RoleBindingRow, SkillRow, TeamRow, UserRow
from datakeel.storage.identity_store import role_in_session, user_in_session
from datakeel.storage.production_projects import record_project_member


def _required(value: str | None, field: str) -> str:
    if not value:
        msg = f"Identity operation requires {field}"
        raise ValidationError(msg)
    return value


def _bind(session: Session, user_id: str, role_id: str, project_id: str | None) -> None:
    role_in_session(session, role_id)
    row = session.scalar(
        select(RoleBindingRow).where(
            RoleBindingRow.user_id == user_id,
            RoleBindingRow.role_id == role_id,
            RoleBindingRow.project_key == (project_id or ""),
        )
    )
    if row is None:
        session.add(RoleBindingRow(user_id=user_id, role_id=role_id, project_key=project_id or ""))


def _memberships(session: Session, user: User) -> None:
    for identifier in user.team_ids:
        row = session.get(TeamRow, identifier)
        if row is None or Team.model_validate(row.payload).status != "active":
            msg = f"Active team does not exist: {identifier}"
            raise NotFoundError(msg)
    for identifier in user.skill_ids:
        row = session.get(SkillRow, identifier)
        if row is None or Skill.model_validate(row.payload).status != "active":
            msg = f"Active skill does not exist: {identifier}"
            raise NotFoundError(msg)


def _create_user(session: Session, params: ManageUsersParams) -> User:
    identifier = _required(params.user_id, "user_id")
    if session.get(UserRow, identifier) is not None:
        msg = "User identity already exists"
        raise ConflictError(msg)
    first = session.scalar(select(func.count()).select_from(UserRow)) == 0
    user = User(
        id=identifier,
        display_name=params.display_name or identifier,
        status=params.status or "active",
        team_ids=params.team_ids or (),
        skill_ids=params.skill_ids or (),
    )
    _memberships(session, user)
    session.add(UserRow(id=user.id, payload=user.model_dump(mode="json")))
    session.flush()
    roles = params.role_ids or (("administrator",) if first else ())
    for role_id in roles:
        _bind(session, user.id, role_id, params.project_id)
    return user


def _change_user(session: Session, params: ManageUsersParams) -> User:
    user = user_in_session(session, _required(params.user_id, "user_id"))
    if params.operation == "delete":
        user = user.model_copy(update={"status": "deleted"})
    elif params.operation == "update":
        user = User.model_validate(
            {
                **user.model_dump(),
                **{
                    key: value
                    for key in ("display_name", "status", "team_ids", "skill_ids")
                    if (value := getattr(params, key)) is not None
                },
            }
        )
        _memberships(session, user)
    elif params.operation == "bind_role":
        _bind(session, user.id, _required(params.role_id, "role_id"), params.project_id)
    elif params.operation == "unbind_role":
        row = session.scalar(
            select(RoleBindingRow).where(
                RoleBindingRow.user_id == user.id,
                RoleBindingRow.role_id == _required(params.role_id, "role_id"),
                RoleBindingRow.project_key == (params.project_id or ""),
            )
        )
        if row is not None:
            session.delete(row)
    session.merge(UserRow(id=user.id, payload=user.model_dump(mode="json")))
    return user


def _team(session: Session, params: ManageUsersParams) -> OperationResult:
    identifier = _required(params.team_id, "team_id")
    row = session.get(TeamRow, identifier)
    if params.operation == "create_team":
        if row is not None:
            msg = "Team identity already exists"
            raise ConflictError(msg)
        team = Team(id=identifier, name=_required(params.name, "name"), leader_id=params.leader_id)
    else:
        if row is None:
            msg = "Team does not exist"
            raise NotFoundError(msg)
        team = Team.model_validate(row.payload)
        team = team.model_copy(
            update={
                "name": params.name or team.name,
                "leader_id": params.leader_id or team.leader_id,
                "status": "deleted" if params.operation == "delete_team" else team.status,
            }
        )
    if team.leader_id:
        user_in_session(session, team.leader_id)
    session.merge(TeamRow(id=team.id, payload=team.model_dump(mode="json")))
    return OperationResult(
        outputs=[AssetRef(asset_type="team", asset_id=team.id)],
        details={"team": team.model_dump(mode="json")},
    )


def manage_users(session: Session, plan: ActionPlan, params: ManageUsersParams) -> OperationResult:
    """Maintain users and memberships without opening an alternate role-grant path."""
    if params.operation.endswith("team"):
        return _team(session, params)
    require_binding_authority(session, plan.actor, params)
    user = (
        _create_user(session, params)
        if params.operation == "create"
        else _change_user(session, params)
    )
    suggest = False
    if params.operation in {"create", "bind_role"}:
        projects = {params.project_id} if params.project_id else set[str]()
        for role_id in (*params.role_ids, *([params.role_id] if params.role_id else [])):
            target = role_in_session(session, role_id).project_id
            if target:
                projects.add(target)
        for project_id in sorted(projects):
            suggest = record_project_member(session, project_id, user.id) or suggest
    return OperationResult(
        outputs=[AssetRef(asset_type="user", asset_id=user.id)],
        details={"user": user.model_dump(mode="json"), "suggest_review": suggest},
    )


def manage_skills(session: Session, params: ManageSkillsParams) -> OperationResult:
    """Create, revise, or archive a skill vocabulary identity."""
    row = session.get(SkillRow, params.skill_id)
    if params.operation == "create":
        if row is not None:
            msg = "Skill identity already exists"
            raise ConflictError(msg)
        skill = Skill(
            id=params.skill_id,
            name=_required(params.name, "name"),
            annotation_type=_required(params.annotation_type, "annotation_type"),
            domain=_required(params.domain, "domain"),
            level=params.level or 1,
        )
    else:
        if row is None:
            msg = "Skill does not exist"
            raise NotFoundError(msg)
        skill = Skill.model_validate(row.payload)
        updates = {
            key: value
            for key in ("name", "annotation_type", "domain", "level")
            if (value := getattr(params, key)) is not None
        }
        if params.operation == "delete":
            updates["status"] = "deleted"
        skill = Skill.model_validate({**skill.model_dump(), **updates})
    session.merge(SkillRow(id=skill.id, payload=skill.model_dump(mode="json")))
    return OperationResult(
        outputs=[AssetRef(asset_type="skill", asset_id=skill.id)],
        details={"skill": skill.model_dump(mode="json")},
    )
