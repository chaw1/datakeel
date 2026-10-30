# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Describe each planned step from its final parameters, the way a person reads them.

Every line is generated from the checked parameters, never from the model's own wording,
so a card can only say what a confirmation would really do. Identities show names, lists
show counts and the first few names, defaults are marked, and label set edits show what is
added and removed with the annotations that change.
"""

import json

from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.errors import NotFoundError
from datakeel.core.intent_models import ChainStep, StepDetail
from datakeel.intents.catalog import FIELD_KINDS, LIST_KINDS, EntityCatalog
from datakeel.intents.edits import label_diff
from datakeel.intents.wording import FIELD_LABELS, field_label
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import Database
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


def _reference(value: dict[str, JsonValue], language: str) -> str:
    source = str(value["$ref"]).split(".", 1)
    step, output = source[0], source[-1]
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
    names = [
        str(item.properties.get("filename") or item.properties.get("name") or "?") for item in found
    ]
    count = f"{len(names)} 个文件" if language == "zh" else f"{len(names)} files"
    return f"{count}: {_listing(names, language)}" if names else count


def task_positions(db: Database, ids: list[JsonValue], language: str) -> list[str]:
    """Tasks have no names: show their position in the project's task list, as people see it."""
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
        names.append(f"第 {position} 个" if language == "zh" else f"#{position}")
    return names


def _labels(value: list[JsonValue], language: str) -> str:
    names = [str(item.get("name")) for item in value if isinstance(item, dict) and item.get("name")]
    return _listing(names, language)


def _plain(value: JsonValue, language: str, field: str = "") -> str:
    if field in {"labels", "add_labels"} and isinstance(value, list):
        return _labels(value, language)
    if isinstance(value, bool):
        return ("是" if value else "否") if language == "zh" else ("yes" if value else "no")
    if isinstance(value, (dict, list)):
        return _shorten(json.dumps(value, ensure_ascii=False))
    return _shorten(str(value))


def _nested(value: JsonValue, catalog: EntityCatalog, language: str) -> str:
    """A structured value as "name: value" pairs; known identities read as their names."""
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
        return known.label if known is not None else value
    return _plain(value, language)


def _value(
    db: Database, field: str, value: JsonValue, catalog: EntityCatalog, language: str
) -> str:
    if isinstance(value, dict) and "$ref" in value:
        return _reference(value, language)
    if field in FIELD_KINDS and isinstance(value, str):
        return _name(FIELD_KINDS[field], value, catalog)
    if field in LIST_KINDS and isinstance(value, list):
        return _listing([_name(LIST_KINDS[field], item, catalog) for item in value], language)
    if field == "selection" and isinstance(value, dict):
        return _selection(db, value, language)
    if field in {"task_id", "task_ids"}:
        values: list[JsonValue] = value if isinstance(value, list) else [value]
        count = f"{len(values)} 个任务" if language == "zh" else f"{len(values)} tasks"
        return f"{count}: {_listing(task_positions(db, values, language), language)}"
    nested = isinstance(value, (dict, list)) and field not in {"labels", "add_labels"}
    return _shorten(_nested(value, catalog, language)) if nested else _plain(value, language, field)


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
        details.append(
            StepDetail(
                label=field_label(name, language), value=f"{default} ({marker})", tone="default"
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
        key = next(iter(step.items[0]))
        values = [item[key] for item in step.items]
        details.append(
            StepDetail(
                label=field_label(key, language), value=_items(db, key, values, catalog, language)
            )
        )
    return details + _diff(db, step, language) + _defaults(step, language)
