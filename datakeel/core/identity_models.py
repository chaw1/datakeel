# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable people, teams, role bindings, and production skill identities."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.models import AssetRef, BoundaryModel, utcnow


class User(BoundaryModel):
    """Identify an actor without treating caller-declared scopes as authority."""

    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    status: Literal["active", "disabled", "deleted"] = "active"
    team_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utcnow)


class Team(BoundaryModel):
    """Group registered people under an optional registered team leader."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    leader_id: str | None = None
    status: Literal["active", "deleted"] = "active"


class Skill(BoundaryModel):
    """Describe an annotation capability and domain, reserved for later matching."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    annotation_type: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    level: int = Field(default=1, ge=1, le=10)
    status: Literal["active", "deleted"] = "active"


class Role(BoundaryModel):
    """Name registered action scopes, globally or for one production project."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    scopes: tuple[str, ...] = ()
    project_id: str | None = None
    description: str = ""
    template: bool = False
    revision: int = Field(default=1, ge=1)
    status: Literal["active", "deleted"] = "active"

    @property
    def asset_ref(self) -> AssetRef:
        """Expose the same stable reference shape used by other ontology objects."""
        return AssetRef(asset_type="role", asset_id=self.id, display_name=self.name)


class RoleBinding(BoundaryModel):
    """Bind an actor to a role, optionally narrowing a global template to a project."""

    user_id: str
    role_id: str
    project_id: str | None = None


class EffectiveScopes(BoundaryModel):
    """Report current server authority and the legacy zero-user compatibility mode."""

    actor: str
    project_id: str | None = None
    scopes: tuple[str, ...] = ()
    zero_users: bool = False
