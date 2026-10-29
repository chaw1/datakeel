# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed JSON identity facts and unique actor-role bindings."""

from pydantic import JsonValue
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id
from datakeel.storage.base import Base


class UserRow(Base):
    """Retain archived users so deleting accounts never reopens anonymous writes."""

    __tablename__ = "identity_users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class TeamRow(Base):
    """Store team facts under the common stable ontology identity."""

    __tablename__ = "identity_teams"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class SkillRow(Base):
    """Store the production skill vocabulary."""

    __tablename__ = "identity_skills"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class RoleRow(Base):
    """Store approved role overrides and user-defined roles."""

    __tablename__ = "identity_roles"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class RoleBindingRow(Base):
    """Keep duplicate global and project-local bindings impossible in both dialects."""

    __tablename__ = "identity_role_bindings"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "project_key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("identity_users.id"), index=True)
    role_id: Mapped[str] = mapped_column(String, index=True)
    project_key: Mapped[str] = mapped_column(String, default="")
