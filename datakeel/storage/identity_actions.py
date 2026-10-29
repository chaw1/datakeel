# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare and apply approved role definitions and controlled identity mutations."""

from sqlalchemy.orm import Session

from datakeel.actions.identity_parameters import (
    DefineRoleParams,
    IdentityActionParams,
    ManageSkillsParams,
    ManageUsersParams,
    UpdateRoleParams,
)
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.registry import POLICIES
from datakeel.core.catalog_canonical import document_hash
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.identity_models import Role
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.storage.identity_authorization import validate_role_scopes
from datakeel.storage.identity_mutations import manage_skills, manage_users
from datakeel.storage.identity_rows import RoleRow, SkillRow, TeamRow, UserRow
from datakeel.storage.identity_store import bindings_in_session, role_in_session


def prepare_identity_params(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Freeze role revisions and show every permitted and denied action before approval."""
    if not isinstance(params, DefineRoleParams):
        return params
    validate_role_scopes(params.scopes)
    if isinstance(params, UpdateRoleParams):
        current = role_in_session(session, params.role_id)
        if params.project_id != current.project_id:
            msg = "A role's project scope is immutable; define a new role for another scope"
            raise ConflictError(msg)
        if params.expected_revision is not None and params.expected_revision != current.revision:
            msg = "Role revision changed before preparation"
            raise ConflictError(msg)
        params = params.model_copy(update={"expected_revision": current.revision})
    else:
        try:
            role_in_session(session, params.role_id)
        except NotFoundError:
            pass
        else:
            msg = "Role identity already exists; use update_role"
            raise ConflictError(msg)
    return params.model_copy(
        update={
            "scopes": tuple(sorted(set(params.scopes))),
            "allowed_actions": tuple(
                sorted(name for name, policy in POLICIES.items() if policy[0] in params.scopes)
            ),
            "denied_actions": tuple(
                sorted(name for name, policy in POLICIES.items() if policy[0] not in params.scopes)
            ),
        }
    )


def _role_action(session: Session, params: DefineRoleParams) -> OperationResult:
    revision = (
        params.expected_revision + 1
        if isinstance(params, UpdateRoleParams) and params.expected_revision
        else 1
    )
    role = Role(
        id=params.role_id,
        name=params.name,
        scopes=params.scopes,
        project_id=params.project_id,
        description=params.description,
        template=role_in_session(session, params.role_id).template
        if isinstance(params, UpdateRoleParams)
        else False,
        revision=revision,
    )
    session.merge(RoleRow(id=role.id, payload=role.model_dump(mode="json")))
    return OperationResult(outputs=[role.asset_ref], details={"role": role.model_dump(mode="json")})


def execute_identity_action(
    session: Session, plan: ActionPlan, params: IdentityActionParams
) -> OperationResult:
    """Mutate identity facts only inside the controlled action transaction."""
    if isinstance(params, ManageUsersParams):
        return manage_users(session, plan, params)
    if isinstance(params, ManageSkillsParams):
        return manage_skills(session, params)
    return _role_action(session, params)


def identity_state(session: Session, params: IdentityActionParams) -> str:
    """Bind a plan to its exact target facts without invalidating unrelated plans."""
    values: dict[str, object] = {}
    if isinstance(params, DefineRoleParams):
        try:
            values["role"] = role_in_session(session, params.role_id).model_dump(mode="json")
        except NotFoundError:
            values["role"] = None
    elif isinstance(params, ManageSkillsParams):
        row = session.get(SkillRow, params.skill_id)
        values["skill"] = row.payload if row else None
    elif params.operation.endswith("team"):
        row = session.get(TeamRow, params.team_id) if params.team_id else None
        values["team"] = row.payload if row else None
    else:
        row = session.get(UserRow, params.user_id) if params.user_id else None
        values["user"] = row.payload if row else None
        values["bindings"] = [
            binding.model_dump(mode="json")
            for binding in bindings_in_session(session, params.user_id or "")
        ]
    return document_hash(JsonDocument.model_validate(values))
