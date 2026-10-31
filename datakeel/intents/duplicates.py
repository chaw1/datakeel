# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A step that creates something never collides silently with what already exists.

The registry below names, per creating action, the parameters that hold the new object's
name (the resolver never looks these up). When one of them names an existing object, the
person is told and asked whether to use the existing one or pick another name; this holds
whether or not the words said 新建, in a single step or inside a chain. A release tag the
dataset already has is taken the same way, so a published version is never published again.

When what the words ask for and the state disagree (a pre-label run with a model that only
does another annotation type), the mismatch is said and the usable models are offered.
"""

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError
from datakeel.core.intent_models import Candidate, Clarification
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.intents.catalog import CatalogEntry, EntityCatalog
from datakeel.intents.drafts import DraftStep
from datakeel.intents.plain_words import enum_label
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import latest_label_set
from datakeel.storage.production_objects import production_objects
from datakeel.storage.release_service import list_releases

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
    "release": ("发布版本", "release"),
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


def taken(db: Database, step: DraftStep, catalog: EntityCatalog) -> CatalogEntry | None:
    """The existing object a new name collides with, release tags of the dataset included."""
    found = existing(step, catalog)
    dataset, tag = step.params.get("dataset_id"), step.params.get("tag")
    if found is not None or step.action != "publish_release":
        return found
    if not isinstance(dataset, str) or not isinstance(tag, str):
        return None
    try:
        releases = list_releases(db, dataset)
    except NotFoundError:
        return None
    wanted = tag.strip().casefold()
    return next(
        (
            CatalogEntry(kind="release", id=release.id, label=release.tag)
            for release in releases
            if release.tag.strip().casefold() == wanted
        ),
        None,
    )


def duplicate_question(step: DraftStep, found: CatalogEntry, language: str) -> Clarification:
    """Say the name is taken; offer the existing object or another name, never a copy."""
    zh, en = KIND_WORDS.get(found.kind, ("对象", "object"))
    release = found.kind == "release"
    if language == "zh":
        other = "换个版本号" if release else "换个名字新建"
        question = f"已经有一个叫「{found.label}」的{zh}了。要用现有的这个, 还是{other}?"
    else:
        other = "publish under another tag" if release else "create it under another name"
        question = (
            f'There is already a {en} called "{found.label}". Use the existing one, or {other}?'
        )

    return Clarification(question=question, action=step.action, fields=[])


def _runs_prelabel(properties: dict[str, JsonValue]) -> bool:
    """What the pre-label run accepts today: an offline model that draws boxes."""
    capabilities = properties.get("capabilities")
    return (
        properties.get("provider") == "fake"
        and isinstance(capabilities, list)
        and "box" in capabilities
    )


def model_question(db: Database, step: DraftStep, language: str) -> Clarification | None:
    """A pre-label run with a model that cannot draw boxes: say what it does, offer others."""
    wanted = step.params.get("model_id")
    if step.action != "run_prelabel" or not isinstance(wanted, str):
        return None
    query = ProductionObjectQuery(kind="model")
    models = {item.asset_ref.asset_id: item.properties for item in production_objects(db, query)}
    chosen = models.get(wanted)
    if chosen is None or _runs_prelabel(chosen):
        return None
    raw = chosen.get("capabilities")
    kinds = [enum_label(str(kind), language) for kind in raw] if isinstance(raw, list) else []
    name = str(chosen.get("name") or wanted)
    usable = [
        Candidate(id=key, label=str(properties.get("name") or key), kind="model")
        for key, properties in models.items()
        if _runs_prelabel(properties)
    ]
    offered = "、".join(item.label for item in usable)
    if language == "zh":
        does = f"做的是{'、'.join(kinds)}标注" if kinds else "不是框标注模型"
        ask = f"要换成{offered}吗?" if usable else "要先登记一个框标注模型吗?"
        question = f"「{name}」{does}, 现在预标注只能用框标注模型。{ask}"
    else:
        does = f"does {', '.join(kinds)}" if kinds else "is not a box model"
        ask = f"Use {offered} instead?" if usable else "Register a box model first?"
        question = f'"{name}" {does}; pre-labelling only runs box models now. {ask}'
    return Clarification(
        question=question, action=step.action, fields=["model_id"], candidates=usable
    )


def unpublished_question(
    db: Database, step: DraftStep, earlier: list[str], language: str
) -> Clarification | None:
    """A project on a label set version nobody published: say so, ask before planning it.

    ``earlier`` are the actions of the steps before this one; a publish there publishes it.
    """
    label_set, version = step.params.get("label_set_id"), step.params.get("label_set_version")
    if step.action != "create_project" or "publish_label_set" in earlier:
        return None
    if not isinstance(label_set, str) or not isinstance(version, int):
        return None
    found = latest_label_set(db, label_set, version)
    if found is None or found.published:
        return None
    question = (
        f"「{found.name}」第 {version} 版还没有发布, 建项目只能用已发布的版本。"
        f"要先发布第 {version} 版, 还是用已发布的版本?"
        if language == "zh"
        else f'Version {version} of "{found.name}" is not published, and a project needs a '
        f"published version. Publish version {version} first, or use a published one?"
    )
    return Clarification(question=question, action=step.action, fields=["label_set_version"])
