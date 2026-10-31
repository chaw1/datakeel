# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A step that creates something never collides silently with what already exists.

The registry below names, per creating action, the parameters that hold the new object's
name (the resolver never looks these up). When one of them names an existing object, the
person is told and asked whether to use the existing one or pick another name; this holds
whether or not the words said 新建, in a single step or inside a chain.
"""

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification
from datakeel.intents.catalog import CatalogEntry, EntityCatalog
from datakeel.intents.drafts import DraftStep

# (action, operation) -> (catalog kind, parameters holding the new name or id).
CREATES: dict[tuple[str, str | None], tuple[str, tuple[str, ...]]] = {
    ("create_project", None): ("project", ("name",)),
    ("create_label_set", None): ("label_set", ("name",)),
    ("draft_label_set", None): ("label_set", ("name",)),
    ("manage_skills", "create"): ("skill", ("skill_id", "name")),
    ("define_role", None): ("role", ("role_id", "name")),
    ("manage_users", "create"): ("user", ("user_id",)),
    ("manage_users", "create_team"): ("team", ("team_id", "name")),
    ("register_model", None): ("model", ("id", "label")),
}
KIND_WORDS = {
    "project": ("项目", "project"),
    "label_set": ("标签集", "label set"),
    "skill": ("技能", "skill"),
    "role": ("角色", "role"),
    "user": ("账号", "account"),
    "team": ("团队", "team"),
    "model": ("模型", "model"),
}


def new_name_fields(action: str, params: dict[str, JsonValue]) -> tuple[str, ...]:
    """Parameters that name the object this step creates; never resolved as references."""
    operation = params.get("operation")
    key = (action, operation if isinstance(operation, str) else None)
    entry = CREATES.get(key) or CREATES.get((action, None))
    return entry[1] if entry is not None else ()


def _values(action: str, params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if action != "register_model":
        return params
    model = params.get("model")
    if not isinstance(model, dict):
        return {}
    name, version = model.get("name"), model.get("version")
    label = f"{name} {version}" if version else name
    return {"id": model.get("id"), "label": label}


def existing(step: DraftStep, catalog: EntityCatalog) -> CatalogEntry | None:
    """The existing object a creating step's new name collides with, if any."""
    if step.action == "create_label_set" and "label_set_id" in step.params:
        return None  # an edit of that label set, not a new one
    operation = step.params.get("operation")
    key = (step.action, operation if isinstance(operation, str) else None)
    entry = CREATES.get(key) or CREATES.get((step.action, None))
    if entry is None:
        return None
    kind, fields = entry
    values = _values(step.action, step.params)
    for field in fields:
        value = values.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        wanted = value.strip().casefold()
        for item in catalog.of(kind):
            if wanted in {name.strip().casefold() for name in (item.label, *item.names)}:
                return item
    return None


def duplicate_question(step: DraftStep, found: CatalogEntry, language: str) -> Clarification:
    """Say the name is taken; offer the existing object or another name, never a copy."""
    zh, en = KIND_WORDS.get(found.kind, ("对象", "object"))
    if language == "zh":
        question = f"已经有一个叫「{found.label}」的{zh}了。要用现有的这个, 还是换个名字新建?"
    else:
        question = (
            f'There is already a {en} called "{found.label}". Use the existing one, '
            "or create it under another name?"
        )
    return Clarification(question=question, action=step.action, fields=[])
