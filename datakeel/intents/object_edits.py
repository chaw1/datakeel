# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""New objects get their id from their name; a person's lists change from what they hold.

A sentence that creates a skill, role, team or person names it ("a skill called vehicle
box"); its id is derived from that name and never looked up as an existing object or asked
for. "Give Li the vehicle box skill" adds to Li's skills: ``add_skill_ids`` and
``remove_skill_ids`` (and the team equivalents) are applied to the lists the person holds
now, because ``skill_ids`` on its own replaces the whole list.
"""

import re

from pydantic import JsonValue

from datakeel.actions.registry import POLICIES
from datakeel.core.errors import NotFoundError
from datakeel.core.production_catalog_models import ProductionModel
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.storage.database import Database
from datakeel.storage.identity_store import get_bindings, get_role, list_users
from datakeel.storage.production_catalog import require_model
from datakeel.storage.production_objects import production_objects

# (action, operation) -> (the new object's id field, the field that names it)
NEW_OBJECTS: dict[tuple[str, str | None], tuple[str, str]] = {
    ("manage_skills", "create"): ("skill_id", "name"),
    ("manage_users", "create"): ("user_id", "display_name"),
    ("manage_users", "create_team"): ("team_id", "name"),
    ("define_role", None): ("role_id", "name"),
}
LIST_EDITS = {
    "add_skill_ids": ("skill_ids", True),
    "remove_skill_ids": ("skill_ids", False),
    "add_team_ids": ("team_ids", True),
    "remove_team_ids": ("team_ids", False),
}
# Values an operation needs although its schema marks them optional (checked at execution).
OPERATION_NEEDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("manage_skills", "create"): ("name", "annotation_type", "domain"),
    ("manage_users", "create"): ("user_id",),
    ("manage_users", "update"): ("user_id",),
    ("manage_users", "delete"): ("user_id",),
    ("manage_users", "bind_role"): ("user_id", "role_id"),
    ("manage_users", "unbind_role"): ("user_id", "role_id"),
    ("manage_users", "create_team"): ("team_id", "name"),
    ("manage_users", "update_team"): ("team_id",),
    ("manage_users", "delete_team"): ("team_id",),
}
_SPACES = re.compile(r"\s+")


def operation_needs(action: str, params: dict[str, JsonValue]) -> list[str]:
    """Values this operation will require at execution that the step leaves out."""
    operation = params.get("operation")
    needed = OPERATION_NEEDS.get((action, operation)) if isinstance(operation, str) else None
    return [name for name in needed or () if params.get(name) in (None, "")]


def new_object_field(action: str, params: dict[str, JsonValue]) -> str | None:
    """The id field naming the object this step creates, filled from its name if missing."""
    operation = params.get("operation")
    key = (action, operation if isinstance(operation, str) else None)
    entry = NEW_OBJECTS.get(key) or NEW_OBJECTS.get((action, None))
    if entry is None:
        return None
    field, naming = entry
    name = params.get(naming)
    if field not in params and isinstance(name, str) and name.strip():
        params[field] = _SPACES.sub("-", name.strip().casefold())[:100]
    return field


def prepare_user_edit(db: Database, params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Apply spoken additions and removals to the skills and teams a person holds now."""
    edits = {key: params.pop(key) for key in list(params) if key in LIST_EDITS}
    if not edits:
        return params
    user_id = params.get("user_id")
    user = next((item for item in list_users(db) if item.id == user_id), None)
    held: dict[str, list[JsonValue]] = {
        "skill_ids": list(user.skill_ids) if user else [],
        "team_ids": list(user.team_ids) if user else [],
    }
    for key, value in edits.items():
        target, adding = LIST_EDITS[key]
        current = params.get(target)
        items = list(current) if isinstance(current, list) else held[target]
        values = value if isinstance(value, list) else [value]
        if adding:
            items += [item for item in values if item not in items]
        else:
            items = [item for item in items if item not in values]
        params[target] = items
    return params


def _scopes(params: dict[str, JsonValue], held: tuple[str, ...]) -> list[JsonValue]:
    """A role's scopes after the actions said to allow or deny; execution reads only scopes."""
    said = params.get("scopes")
    # A scope the model made up ("review") is no scope; the actions said carry the meaning.
    known = {policy[0] for policy in POLICIES.values()}
    scopes = {str(item) for item in said} & known if isinstance(said, list) else set(held)
    for key, adding in (("allowed_actions", True), ("denied_actions", False)):
        listed = params.get(key)
        names = [str(item) for item in listed] if isinstance(listed, list) else []
        found = {POLICIES[name][0] for name in names if name in POLICIES}
        scopes = scopes | found if adding else scopes - found
    ordered: list[JsonValue] = [*sorted(scopes)]
    return ordered


def prepare_update(db: Database, action: str, params: dict[str, JsonValue]) -> None:
    """An edit keeps what the words leave unsaid, at the revision it was read from."""
    if action in {"define_role", "update_role"}:
        try:
            role = get_role(db, str(params.get("role_id"))) if action == "update_role" else None
        except NotFoundError:
            role = None
        if role is not None:
            kept = {
                "name": role.name,
                "description": role.description,
                "project_id": role.project_id,
            }
            params.update(
                {key: value for key, value in kept.items() if value and key not in params}
            )
            params.setdefault("expected_revision", role.revision)
        params["scopes"] = _scopes(params, role.scopes if role is not None else ())
    model = params.get("model")
    if action != "update_model" or not isinstance(model, dict):
        return
    current = current_model(db, model)
    if current is None:
        return
    stored = current.model_dump(mode="json", exclude={"revision"})
    if str(model.get("name", "")).casefold() == f"{current.name} {current.version}".casefold():
        # The catalog shows "name version": that label is not a new name.
        model = {key: value for key, value in model.items() if key != "name"}
    params["model"] = {**stored, **model, "id": current.id}
    params.setdefault("expected_revision", current.revision)


def bound_projects(db: Database, params: dict[str, JsonValue]) -> list[str]:
    """Projects the person given a role already works in, when the step names no project."""
    user = params.get("user_id")
    if params.get("operation") != "bind_role" or params.get("project_id"):
        return []
    try:
        bindings = get_bindings(db, user) if isinstance(user, str) else ()
    except NotFoundError:
        return []
    return sorted({item.project_id for item in bindings if item.project_id})


def current_model(db: Database, model: dict[str, JsonValue]) -> ProductionModel | None:
    """The stored model a change names, by its identity or by its name as said."""
    wanted = str(model.get("id") or model.get("name") or "").strip().casefold()
    query = ProductionObjectQuery(kind="model")
    for item in production_objects(db, query):
        name = str(item.properties.get("name", ""))
        shown = f"{name} {item.properties.get('version', '')}".strip()  # as the catalog shows it
        if wanted in {item.asset_ref.asset_id.casefold(), name.casefold(), shown.casefold()}:
            try:
                with db.session() as session:
                    return require_model(session, item.asset_ref.asset_id)
            except NotFoundError:
                return None
    return None
