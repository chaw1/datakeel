# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled identity and role parameters, including reviewable action grants."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel


class ManageUsersParams(BoundaryModel):
    """Create, revise, archive, or bind registered people and teams."""

    request_id: str = Field(min_length=1, max_length=200)
    operation: Literal[
        "create",
        "update",
        "delete",
        "bind_role",
        "unbind_role",
        "create_team",
        "update_team",
        "delete_team",
    ]
    user_id: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, min_length=1)
    status: Literal["active", "disabled"] | None = None
    role_id: str | None = None
    role_ids: tuple[str, ...] = ()
    project_id: str | None = None
    team_id: str | None = None
    name: str | None = None
    leader_id: str | None = None
    team_ids: tuple[str, ...] | None = None
    skill_ids: tuple[str, ...] | None = None


class ManageSkillsParams(BoundaryModel):
    """Maintain skill metadata without enabling skill-based dispatch."""

    request_id: str = Field(min_length=1, max_length=200)
    operation: Literal["create", "update", "delete"]
    skill_id: str = Field(min_length=1)
    name: str | None = None
    annotation_type: str | None = None
    domain: str | None = None
    level: int | None = Field(default=None, ge=1, le=10)


class DefineRoleParams(BoundaryModel):
    """Prepare a new role whose permissions become effective only after approval."""

    request_id: str = Field(min_length=1, max_length=200)
    role_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scopes: tuple[str, ...] = ()
    project_id: str | None = None
    description: str = ""
    allowed_actions: tuple[str, ...] = ()
    denied_actions: tuple[str, ...] = ()


class UpdateRoleParams(DefineRoleParams):
    """Replace one approved role revision while preserving its stable identity."""

    expected_revision: int | None = Field(default=None, ge=1)


IdentityActionParams = ManageUsersParams | ManageSkillsParams | DefineRoleParams | UpdateRoleParams

IDENTITY_PARAMETER_TYPES: dict[str, type[BoundaryModel]] = {
    "manage_users": ManageUsersParams,
    "manage_skills": ManageSkillsParams,
    "define_role": DefineRoleParams,
    "update_role": UpdateRoleParams,
}

IDENTITY_POLICIES: dict[str, tuple[str, bool, str]] = {
    "manage_users": ("users:manage", True, "Manage registered users, team membership and roles"),
    "manage_skills": ("skills:manage", True, "Manage annotation skill metadata"),
    "define_role": ("roles:manage", False, "Approve a new explicitly bounded role"),
    "update_role": ("roles:manage", False, "Approve a replacement role revision"),
}
