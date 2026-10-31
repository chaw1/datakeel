# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Describe each planned step from its final parameters, the way a person reads them.

Every line is generated from the checked parameters, never from the model's own wording,
so a card can only say what a confirmation would really do. Identities show names, lists
show counts and the first few names, defaults are marked, and label set edits show what is
added and removed with the annotations that change.
"""

import json
from collections.abc import Callable

from pydantic import BaseModel, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.errors import NotFoundError
from datakeel.core.intent_models import ChainStep, StepDetail
from datakeel.intents.capability import cloud_prelabel
from datakeel.intents.catalog import FIELD_KINDS, LIST_KINDS, EntityCatalog
from datakeel.intents.edits import label_diff
from datakeel.intents.plain_words import enum_label
from datakeel.intents.scope_words import scope_words
from datakeel.intents.signatures import choice_fields
from datakeel.intents.wording import FIELD_LABELS, action_title, field_label
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_files
from datakeel.storage.identity_store import list_users
from datakeel.storage.object_queries import evaluate
from datakeel.storage.production_queries import get_task, list_tasks

HIDDEN = frozenset(
    {
        "request_id",
        "expected_revision",
        "prepared",
        "target",
        "operation",
        "previous_version",
        # Derived from the label difference, which the card already shows in words.
        "migration",
    }
)
REVISIONS = frozenset({"revision_id", "previous_revision_id"})
PREVIEW = 3
TEXT_LIMIT = 120


def _shorten(text: str) -> str:
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def _listing(names: list[str], language: str) -> str:
    shown = "、".join(names[:PREVIEW]) if language == "zh" else ", ".join(names[:PREVIEW])
    if len(names) <= PREVIEW:
        return shown
    return (
        f"{shown} 等 {len(names)} 个"
        if language == "zh"
        else f"{shown} and {len(names) - PREVIEW} more"
    )


def _name(kind: str, value: JsonValue, catalog: EntityCatalog) -> str:
    entry = catalog.get(kind, value) if isinstance(value, str) else None
    return entry.label if entry is not None else str(value)


def _step_name(step: str, language: str) -> str:
    """Step "s2" reads as 第 2 步 / step 2."""
    number = step.removeprefix("s")
    if not number.isdigit():
        return "前一步" if language == "zh" else "an earlier step"
    return f"第 {number} 步" if language == "zh" else f"step {number}"


def _reference(value: dict[str, JsonValue], language: str) -> str:
    source = str(value["$ref"]).split(".", 1)
    step, output = _step_name(source[0], language), source[-1]
    label = field_label(
        output.removesuffix("_version") + ("_id" if output.endswith("_version") else ""), language
    )
    if output.endswith("_version"):
        return (
            f"{step} 生成的{label}版本" if language == "zh" else f"the {label} version from {step}"
        )
    position = value.get("$nth")
    if isinstance(position, int):
        return (
            f"{step} 生成的第 {position} 个{label}"
            if language == "zh"
            else f"item {position} of the {label} created by {step}"
        )
    return f"{step} 生成的{label}" if language == "zh" else f"the {label} created by {step}"


def _selection(db: Database, value: dict[str, JsonValue], language: str) -> str:
    try:
        found = evaluate(db, ObjectSet.model_validate(value)).objects
    except (ModelValidationError, ValueError):
        return _shorten(json.dumps(value, ensure_ascii=False))
    dataset = value.get("dataset_id")
    try:
        listed = list_files(db, dataset) if isinstance(dataset, str) else []
    except NotFoundError:
        listed = []
    # Files are named in the order the dataset lists them, like everywhere else.
    order = {item.id: position for position, item in enumerate(listed)}
    found = sorted(found, key=lambda item: order.get(item.asset_ref.asset_id, len(order)))
    names = [
        str(item.properties.get("filename") or item.properties.get("name") or "?") for item in found
    ]
    count = f"{len(names)} 个文件" if language == "zh" else f"{len(names)} files"
    return f"{count}: {_listing(names, language)}" if names else count


def task_positions(db: Database, ids: list[JsonValue]) -> list[str]:
    """Tasks have no names: show their list number (#N), the one the task list shows."""
    order: dict[str, int] = {}
    names: list[str] = []
    for value in ids:
        try:
            task = get_task(db, str(value))
        except NotFoundError:
            names.append("?")
            continue
        if task.id not in order:
            listed = list_tasks(db, task.project_id)
            order.update({item.id: index for index, item in enumerate(listed, start=1)})
        position = order.get(task.id, 0)
        names.append(f"#{position}")
    return names


def _labels(value: list[JsonValue], language: str) -> str:
    names = [str(item.get("name")) for item in value if isinstance(item, dict) and item.get("name")]
    return _listing(names, language)


def _actions(value: list[JsonValue], language: str) -> str:
    return _listing([action_title(str(item), language) for item in value], language)


def _scopes(value: list[JsonValue], language: str) -> str:
    return scope_words([str(item) for item in value], language)


# Lists whose items are names of labels, actions or permission scopes, said in words.
LIST_WORDS: dict[str, Callable[[list[JsonValue], str], str]] = {
    "labels": _labels,
    "add_labels": _labels,
    "allowed_actions": _actions,
    "scopes": _scopes,
}


def _plain(value: JsonValue, language: str, field: str = "") -> str:
    words = LIST_WORDS.get(field)
    if words is not None and isinstance(value, list):
        return words(value, language)
    if isinstance(value, str) and field in choice_fields():
        return enum_label(value, language)
    if isinstance(value, str) and field in REVISIONS:
        # A revision is read from the task's current state; its identity means nothing here.
        return "最新保存的那一版" if language == "zh" else "the latest saved version"
    if isinstance(value, bool):
        return ("是" if value else "否") if language == "zh" else ("yes" if value else "no")
    if isinstance(value, (dict, list)):
        return _shorten(json.dumps(value, ensure_ascii=False))
    return _shorten(str(value))


def _nested(value: JsonValue, catalog: EntityCatalog, language: str) -> str:
    """A structured value as "name: value" pairs; known identities read as their names."""
    if isinstance(value, dict) and "$ref" in value:
        return _reference(value, language)
    if isinstance(value, dict):
        pairs = [
            f"{field_label(key, language)}: {_nested(item, catalog, language)}"
            for key, item in value.items()
            if key != "request_id"
        ]
        return "; ".join(pairs)
    if isinstance(value, list):
        return _listing([_nested(item, catalog, language) for item in value], language)
    if isinstance(value, str):
        known = next((entry for entry in catalog.entries if entry.id == value), None)
        return known.label if known is not None else enum_label(value, language)
    return _plain(value, language)


def _value(
    db: Database, field: str, value: JsonValue, catalog: EntityCatalog, language: str
) -> str:
    if isinstance(value, dict) and "$ref" in value:
        return _reference(value, language)
    if field in {"task_id", "task_ids"}:
        # Tasks are not in the catalog: they read as their places in the task list.
        values: list[JsonValue] = value if isinstance(value, list) else [value]
        count = f"{len(values)} 个任务" if language == "zh" else f"{len(values)} tasks"
        return f"{count}: {_listing(task_positions(db, values), language)}"
    if field in FIELD_KINDS and isinstance(value, str):
        return _name(FIELD_KINDS[field], value, catalog)
    if field in LIST_KINDS and isinstance(value, list):
        named = [
            _reference(item, language)
            if isinstance(item, dict) and "$ref" in item
            else _name(LIST_KINDS[field], item, catalog)
            for item in value
        ]
        return _listing(named, language)
    if field in {"selection", "model"} and isinstance(value, dict):
        return (
            _selection(db, value, language)
            if field == "selection"
            else _model_words(value, language)
        )
    nested = isinstance(value, (dict, list)) and field not in LIST_WORDS
    return _shorten(_nested(value, catalog, language)) if nested else _plain(value, language, field)


def _model_words(value: dict[str, JsonValue], language: str) -> str:
    """A model definition as its name, version and what it annotates."""
    name = f"{value.get('name') or value.get('id')} {value.get('version') or ''}".strip()
    kinds = value.get("capabilities")
    listed = [enum_label(str(item), language) for item in kinds] if isinstance(kinds, list) else []
    return f"{name} ({_listing(listed, language)})" if listed else name


def _defaults(step: ChainStep, language: str) -> list[StepDetail]:
    model = PARAMETER_TYPES.get(step.action)
    details: list[StepDetail] = []
    for name, field in (model.model_fields if model else {}).items():
        if name in step.params or name in HIDDEN or name not in FIELD_LABELS or field.is_required():
            continue
        default = field.get_default(call_default_factory=True)
        if default in (None, (), [], {}, ""):
            continue
        marker = "默认" if language == "zh" else "default"
        shown = _plain(default, language, name) if isinstance(default, str) else default
        if isinstance(default, BaseModel):
            limits = default.model_dump(mode="json").items()
            shown = ", ".join(f"{field_label(key, language)} {item}" for key, item in limits)
        details.append(
            StepDetail(
                label=field_label(name, language), value=f"{shown} ({marker})", tone="default"
            )
        )
    return details


def _diff(db: Database, step: ChainStep, language: str) -> list[StepDetail]:
    diff = label_diff(db, step.params) if step.action == "create_label_set" else None
    if diff is None:
        return []
    zh = language == "zh"
    lines = [
        StepDetail(
            label="新增标签" if zh else "Added labels",
            value=_listing(diff.added, language),
            tone="added",
        )
        if diff.added
        else None,
        StepDetail(
            label="删除标签" if zh else "Removed labels",
            value=_listing(diff.removed, language),
            tone="removed",
        )
        if diff.removed
        else None,
        StepDetail(
            label="改名" if zh else "Renamed", value=_listing(diff.renamed, language), tone="impact"
        )
        if diff.renamed
        else None,
    ]
    impact = (
        f"保留 {diff.kept} 个标签 · 影响 {diff.affected_annotations} 条标注、"
        f"{diff.affected_revisions} 个修订"
        if zh
        else f"{diff.kept} labels kept · {diff.affected_annotations} annotations and "
        f"{diff.affected_revisions} revisions affected"
    )
    base = f"基于 v{diff.base_version}" if zh else f"based on v{diff.base_version}"
    return [line for line in lines if line is not None] + [
        StepDetail(label=base, value=impact, tone="impact")
    ]


def _samples(db: Database, step: ChainStep, language: str) -> str:
    """Sample files by file name, read from the step's own dataset."""
    ids, dataset = step.params.get("sample_ids"), step.params.get("dataset_id")
    if not isinstance(ids, list) or not isinstance(dataset, str):
        return _plain(ids, language)
    condition: dict[str, JsonValue] = {"field": "id", "operator": "in", "value": ids}
    return _selection(db, {"dataset_id": dataset, "filters": [condition]}, language)


def _items(
    db: Database, key: str, values: list[JsonValue], catalog: EntityCatalog, language: str
) -> str:
    """One step repeated per item: tasks as one list, other items each by name."""
    if key in {"task_id", "task_ids"}:
        return _value(db, "task_ids", values, catalog, language)
    return _listing([_value(db, key, item, catalog, language) for item in values], language)


def describe_step(
    db: Database, step: ChainStep, catalog: EntityCatalog, language: str
) -> list[StepDetail]:
    """Human-readable lines for one checked step, generated only from its parameters."""
    details = [
        StepDetail(
            label=field_label(name, language),
            value=_samples(db, step, language)
            if name == "sample_ids"
            else _value(db, name, value, catalog, language),
        )
        for name, value in step.params.items()
        if name not in HIDDEN
        and not (
            name == "labels" and step.action == "create_label_set" and "label_set_id" in step.params
        )
    ]
    if step.items:
        key = "task_id" if "task_id" in step.items[0] else next(iter(step.items[0]))
        values = [item[key] for item in step.items]
        details.append(
            StepDetail(
                label=field_label(key, language), value=_items(db, key, values, catalog, language)
            )
        )
    return (
        details
        + _diff(db, step, language)
        + _holders(db, step, language)
        + _cloud_spend(db, step, language)
        + _defaults(step, language)
    )


def _cloud_spend(db: Database, step: ChainStep, language: str) -> list[StepDetail]:
    """A cloud pre-label run says how many images go out and the estimate, in its currency."""
    cloud = cloud_prelabel(db, step.params) if step.action == "run_prelabel" else None
    if cloud is None:
        return []
    estimate, over = cloud
    cost = f"{estimate.total:.4g} {estimate.currency}"
    if language == "zh":
        value = f"{estimate.images} 张图发给云端模型, 预计 {cost}" + (
            "; 超过预算, 要签批" if over else ""
        )
        return [StepDetail(label="预计花费", value=value, tone="impact")]
    value = f"{estimate.images} images go to a cloud model, about {cost}" + (
        "; above the budget, so it needs a signature" if over else ""
    )
    return [StepDetail(label="Estimated spend", value=value, tone="impact")]


def _holders(db: Database, step: ChainStep, language: str) -> list[StepDetail]:
    """Changing or retiring a skill shows how many people hold it now."""
    skill = step.params.get("skill_id")
    if step.action != "manage_skills" or step.params.get("operation") == "create":
        return []
    if not isinstance(skill, str):
        return []
    count = sum(skill in user.skill_ids for user in list_users(db) if user.status != "deleted")
    label = "目前持有的人" if language == "zh" else "Held by"
    value = f"{count} 人" if language == "zh" else f"{count} people"
    return [StepDetail(label=label, value=value, tone="impact")]
