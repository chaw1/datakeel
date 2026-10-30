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

from datakeel.storage.database import Database
from datakeel.storage.identity_store import list_users

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
