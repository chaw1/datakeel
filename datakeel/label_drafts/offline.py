# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic drafting from standards, existing labels and annotated samples."""

import hashlib
import re
from collections.abc import Mapping, Sequence

from pydantic import JsonValue, ValidationError

from datakeel.core.label_guidelines import GuidelineExample, LabelGuideline
from datakeel.core.production_attributes import AttributeOption, TemplateAttribute
from datakeel.core.production_catalog_models import ProductionLabel
from datakeel.label_drafts.models import AttributeSource, CategorySource, DraftInputs

EXAMPLES_PER_KIND = 3
OPTION_LIMIT = 20


def label_id(key: str) -> str:
    """Stable ASCII identity from a category key; non-ASCII names get a short digest."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", key).strip("_").casefold()
    if cleaned and cleaned == key.casefold():
        return cleaned
    digest = hashlib.sha256(key.encode()).hexdigest()[:8]
    return f"{cleaned}_{digest}" if cleaned else f"label_{digest}"


def _attribute(source: AttributeSource) -> TemplateAttribute | None:
    kind = (
        "enum"
        if source.options
        else "number"
        if source.data_type in {"int", "integer", "decimal", "float", "number"}
        else "boolean"
        if source.data_type in {"bool", "boolean"}
        else "text"
    )
    try:
        return TemplateAttribute(
            key=re.sub(r"[^A-Za-z0-9_]", "_", source.key)[:64] or "field",
            name_zh=source.name_zh[:100],
            name_en=(source.name_en or source.key)[:100],
            type=kind,
            required=source.required,
            options=tuple(
                AttributeOption(value=value[:100], name_zh=zh[:100], name_en=(en or value)[:100])
                for value, zh, en in source.options
            ),
        )
    except ValidationError:
        return None


def _roots(categories: list[CategorySource]) -> dict[str, str]:
    """The top category key of every category, following parent keys."""
    parents = {item.key: item.parent_key for item in categories}
    roots: dict[str, str] = {}
    for key in parents:
        current, seen = key, {key}
        while (parent := parents.get(current)) and parent in parents and parent not in seen:
            current = parent
            seen.add(current)
        roots[key] = current
    return roots


def build_labels(inputs: DraftInputs) -> list[ProductionLabel]:
    """One label per category, unique by name, each with the attributes of its subtree."""
    built = [(source, _attribute(source)) for source in inputs.attributes]
    labels: list[ProductionLabel] = []
    names: set[str] = set()
    ids: set[str] = set()
    keys: dict[str, str] = {}
    categories = list(inputs.categories) or [
        CategorySource(key=inputs.topic or inputs.name, name_zh=inputs.topic or inputs.name)
    ]
    roots = _roots(categories)
    for category in categories:
        name = (
            category.name_zh
            if inputs.language == "zh" or not category.name_en
            else category.name_en
        )
        identifier = label_id(category.key)
        if name.casefold() in names or identifier in ids:
            continue
        root = roots.get(category.key, category.key)
        scoped = [field for source, field in built if field and source.scope in {None, root}]
        fields = tuple({field.key: field for field in reversed(scoped)}.values())[::-1]
        labels.append(
            ProductionLabel(
                id=identifier,
                name=name,
                parent_id=keys.get(category.parent_key or ""),
                name_zh=category.name_zh,
                name_en=category.name_en
                or (category.name_zh if category.name_zh.isascii() else None),
                fields=fields,
            )
        )
        names.add(name.casefold())
        ids.add(identifier)
        keys[category.key] = identifier
    return labels


def examples_for(label: ProductionLabel, inputs: DraftInputs) -> tuple[GuidelineExample, ...]:
    """Positive samples carry the label; negative ones carry other labels only."""
    spellings = {label.id, label.name, label.name_zh or "", label.name_en or ""} - {""}
    positive = [s.id for s in inputs.samples if spellings & set(s.labels)][:EXAMPLES_PER_KIND]
    negative = [s.id for s in inputs.samples if s.labels and not spellings & set(s.labels)][
        :EXAMPLES_PER_KIND
    ]
    return tuple(
        [GuidelineExample(sample_id=item, kind="positive") for item in positive]
        + [GuidelineExample(sample_id=item, kind="negative") for item in negative]
    )


def _sentence(head: str, descriptions: dict[str, str], identifier: str) -> str:
    return f"{head} {descriptions.get(identifier, '')}".strip()


def offline_rule(label: ProductionLabel, inputs: DraftInputs) -> LabelGuideline:
    """A plain rule for one label, citing annotated samples as its examples."""
    descriptions = {label_id(item.key): item.description for item in inputs.categories}
    return LabelGuideline(
        label_id=label.id,
        text_zh=_sentence(f"标注所有「{label.name_zh or label.name}」。", descriptions, label.id),
        text_en=_sentence(f"Annotate every {label.name_en or label.name}.", descriptions, label.id),
        examples=examples_for(label, inputs),
    )


def _attribute_key(raw: str) -> str:
    """A valid attribute key; a non-ASCII or digit-led name gets a short digest."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_").casefold()[:50]
    if cleaned and cleaned == raw.casefold() and not cleaned[0].isdigit():
        return cleaned
    digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"attr_{cleaned}_{digest}" if cleaned else f"attr_{digest}"


def _typed(values: Sequence[JsonValue]) -> dict[str, JsonValue]:
    present = [value for value in values if value is not None]
    if present and all(isinstance(value, bool) for value in present):
        return {"data_type": "boolean"}
    if present and all(isinstance(value, int | float) for value in present):
        return {"data_type": "number"}
    texts = sorted({value for value in present if isinstance(value, str) and value})
    if texts and len(texts) <= OPTION_LIMIT and all(isinstance(value, str) for value in present):
        return {"options": [[value, value, value] for value in texts]}
    return {"data_type": "text"}


def observed_attributes(
    observed: Mapping[str, Mapping[str, Sequence[JsonValue]]],
) -> tuple[AttributeSource, ...]:
    """Attributes people already filled on each annotated category, typed by their values."""
    return tuple(
        AttributeSource.model_validate(
            {
                "key": _attribute_key(key),
                "name_zh": key[:100],
                "name_en": key[:100],
                "scope": category,
                **_typed(values),
            }
        )
        for category, fields in sorted(observed.items())
        for key, values in sorted(fields.items())
    )
