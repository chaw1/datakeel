# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read registered identities and resolve editable built-in role templates."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.registry import POLICIES
from datakeel.core.errors import NotFoundError
from datakeel.core.identity_models import Role, RoleBinding, Skill, Team, User
from datakeel.storage.database import Database
from datakeel.storage.identity_rows import RoleBindingRow, RoleRow, SkillRow, TeamRow, UserRow

_MANAGER_ACTIONS = frozenset(
    {
        "create_label_set",
        "publish_label_set",
        "create_project",
        "split_packages",
        "run_prelabel",
        "assign_tasks",
        "finalize_project",
        "reopen_task",
        "import_predictions",
        "upgrade_project",
        "configure_project",
        "revoke_assignment",
        "accept_package",
        # Finalized project versions feed controlled training splits and exports.
        "export_dataset",
    }
)


def role_templates() -> tuple[Role, ...]:
    """Derive the five templates exclusively from currently registered action scopes."""
    groups = (
        ("administrator", "Administrator", frozenset(POLICIES)),
        ("project_manager", "Project manager", _MANAGER_ACTIONS),
        (
            "annotator",
            "Annotator",
            frozenset({"claim_task", "release_task", "heartbeat", "save_revision", "submit_task"}),
        ),
        (
            "reviewer",
            "Quality reviewer",
            frozenset({"claim_task", "release_task", "heartbeat", "review_task"}),
        ),
        ("acceptance", "Acceptance observer", frozenset[str]()),
    )
    return tuple(
        Role(
            id=identifier,
            name=name,
            template=True,
            scopes=tuple(sorted({POLICIES[action][0] for action in actions if action in POLICIES})),
            description="Read-only project, sampling and export previews"
            if identifier == "acceptance"
            else "",
        )
        for identifier, name, actions in groups
    )


def role_in_session(session: Session, identifier: str) -> Role:
    """Read an approved override, or an unchanged built-in template."""
    row = session.get(RoleRow, identifier)
    if row is not None:
        return Role.model_validate(row.payload)
    for role in role_templates():
        if role.id == identifier:
            return role
    msg = f"Role does not exist: {identifier}"
    raise NotFoundError(msg)


def user_in_session(session: Session, identifier: str) -> User:
    """Read one registered user, including archived account identities."""
    row = session.get(UserRow, identifier)
    if row is None:
        msg = f"User does not exist: {identifier}"
        raise NotFoundError(msg)
    return User.model_validate(row.payload)


def bindings_in_session(session: Session, user_id: str) -> tuple[RoleBinding, ...]:
    """Return typed global and project-local role memberships."""
    return tuple(
        RoleBinding(user_id=row.user_id, role_id=row.role_id, project_id=row.project_key or None)
        for row in session.scalars(
            select(RoleBindingRow)
            .where(RoleBindingRow.user_id == user_id)
            .order_by(RoleBindingRow.id)
        )
    )


def list_users(db: Database) -> list[User]:
    """List registered identities, retaining archived audit references."""
    with db.session() as session:
        return [
            User.model_validate(row.payload)
            for row in session.scalars(select(UserRow).order_by(UserRow.id))
        ]


def list_teams(db: Database) -> list[Team]:
    """List team facts with their lifecycle state."""
    with db.session() as session:
        return [
            Team.model_validate(row.payload)
            for row in session.scalars(select(TeamRow).order_by(TeamRow.id))
        ]


def list_skills(db: Database) -> list[Skill]:
    """List skill vocabulary without performing dispatch matching."""
    with db.session() as session:
        return [
            Skill.model_validate(row.payload)
            for row in session.scalars(select(SkillRow).order_by(SkillRow.id))
        ]


def list_roles(db: Database) -> list[Role]:
    """List all templates and their approved overrides, plus custom roles."""
    with db.session() as session:
        roles = {role.id: role for role in role_templates()}
        for row in session.scalars(select(RoleRow).order_by(RoleRow.id)):
            roles[row.id] = Role.model_validate(row.payload)
        return [roles[key] for key in sorted(roles)]


def get_role(db: Database, identifier: str) -> Role:
    """Read one role through a short-lived storage session."""
    with db.session() as session:
        return role_in_session(session, identifier)


def get_bindings(db: Database, user_id: str) -> tuple[RoleBinding, ...]:
    """Read an actor's role bindings for administrative inspection."""
    with db.session() as session:
        return bindings_in_session(session, user_id)
