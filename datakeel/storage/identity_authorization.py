# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compute server role authority and check grants at approval and execution."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.actions.identity_parameters import DefineRoleParams, ManageUsersParams
from datakeel.actions.models import ActionPlan
from datakeel.actions.policy import authorize
from datakeel.actions.registry import POLICIES
from datakeel.core.errors import AuthorizationError, ValidationError
from datakeel.core.identity_models import EffectiveScopes, User
from datakeel.storage.identity_rows import UserRow
from datakeel.storage.identity_store import bindings_in_session, role_in_session


def effective_scopes(
    session: Session, actor: str, project_id: str | None = None
) -> EffectiveScopes:
    """Union active global and matching project role scopes, preserving zero-user mode."""
    if session.scalar(select(func.count()).select_from(UserRow)) == 0:
        return EffectiveScopes(actor=actor, project_id=project_id, scopes=("*",), zero_users=True)
    row = session.get(UserRow, actor)
    if row is None or User.model_validate(row.payload).status != "active":
        return EffectiveScopes(actor=actor, project_id=project_id)
    scopes: set[str] = set()
    for binding in bindings_in_session(session, actor):
        role = role_in_session(session, binding.role_id)
        targets = {target for target in (binding.project_id, role.project_id) if target is not None}
        if role.status == "active" and (not targets or targets == {project_id}):
            scopes.update(role.scopes)
    return EffectiveScopes(actor=actor, project_id=project_id, scopes=tuple(sorted(scopes)))


def validate_role_scopes(scopes: tuple[str, ...]) -> None:
    """Reject invented or wildcard grants even when the caller is a local administrator."""
    unknown = set(scopes) - {policy[0] for policy in POLICIES.values()}
    if unknown:
        msg = f"Role scopes are not registered action scopes: {', '.join(sorted(unknown))}"
        raise ValidationError(msg)


def require_grant_authority(
    session: Session, actor: str, scopes: tuple[str, ...], project_id: str | None
) -> None:
    """A grant may never exceed the signer's current server authority at its target."""
    validate_role_scopes(scopes)
    current = effective_scopes(session, actor, project_id)
    if "*" not in current.scopes and not set(scopes).issubset(current.scopes):
        msg = "Role grant exceeds the approving actor's current effective scopes"
        raise AuthorizationError(msg)


def authorize_identity_plan(session: Session, plan: ActionPlan, actor: str) -> None:
    """Recompute action authority from stored bindings and the action's actual project."""
    from datakeel.storage.production_queries import project_for_params  # noqa: PLC0415

    params_project = project_for_params(session, plan.canonical_params)
    current = effective_scopes(session, actor, params_project)
    authorize(plan, actor, effective_scopes=current.scopes)


def require_server_scope(session: Session, plan: ActionPlan, actor: str) -> None:
    """Recheck replay authority without expiring an already executed request."""
    from datakeel.storage.production_queries import project_for_params  # noqa: PLC0415

    current = effective_scopes(session, actor, project_for_params(session, plan.canonical_params))
    scope = POLICIES[plan.action_type][0]
    if "*" not in current.scopes and scope not in current.scopes:
        msg = f"Missing server-authorized action scope: {scope}"
        raise AuthorizationError(msg)


def require_role_grant(session: Session, plan: ActionPlan, actor: str) -> None:
    """Check explicitly granted role scopes at both human approval and execution."""
    if plan.action_type not in {"define_role", "update_role"}:
        return
    params = DefineRoleParams.model_validate(
        {key: value for key, value in plan.canonical_params.items() if key != "expected_revision"}
    )
    require_grant_authority(session, actor, params.scopes, params.project_id)


def require_binding_authority(session: Session, actor: str, params: ManageUsersParams) -> None:
    """Prevent user administration from bypassing the role grant ceiling."""
    for identifier in (*params.role_ids, *([params.role_id] if params.role_id else [])):
        role = role_in_session(session, identifier)
        if role.status != "active":
            msg = "Archived roles cannot be assigned"
            raise ValidationError(msg)
        target = params.project_id or role.project_id
        if role.project_id and params.project_id and role.project_id != params.project_id:
            msg = "A project role cannot be rebound to another project"
            raise ValidationError(msg)
        require_grant_authority(session, actor, role.scopes, target)
