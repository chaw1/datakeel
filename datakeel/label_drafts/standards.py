# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Decide which data standard code lists become labels and which become attributes.

A code list that names kinds of objects (vehicle type, traffic light kinds) becomes a
label subtree: the field becomes the parent label and every entry a child. A code list
that describes a state or property (colour, occlusion, yes or no) becomes an attribute,
attached to the subtree whose name it starts with. A code list whose name says neither is
treated as kinds, so no listed kind silently turns into an attribute. Every decision is
returned with its reason, so the draft records why each code ended up where it did.
"""

import re
from typing import Literal

from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.core.standard_models import CodeList, FieldStandard, StandardsContract
from datakeel.label_drafts.models import AttributeSource, CategorySource

CATEGORY_WORDS = re.compile(
    r"类型|类别|种类|分类|\btypes?\b|\bclass(?:es)?\b|\bcategor(?:y|ies)\b|\bkinds?\b",
    re.IGNORECASE,
)
STATE_WORDS = re.compile(
    r"状态|颜色|朝向|方向|是否|等级|级别|程度|遮挡|截断|可见|清晰|质量|天气|光照|时段|形状|"
    r"材质|尺寸|大小|线型|样式|\bstate\b|\bstatus\b|colou?r|direction|orientation|\blevel\b|"
    r"occlu|truncat|visib|quality|weather|lighting|shape|material|\bsize\b|\bstyle\b|"
    r"^(?:is|has)\b",
    re.IGNORECASE,
)
BOOLEAN_VALUES = frozenset({"yes", "no", "true", "false", "y", "n", "是", "否", "有", "无"})
Decision = Literal["category", "attribute"]


class StandardSources(BoundaryModel):
    """Categories and attributes from data standards, with one note per decision."""

    categories: tuple[CategorySource, ...] = ()
    attributes: tuple[AttributeSource, ...] = ()
    notes: tuple[str, ...] = Field(default_factory=tuple[str, ...])


def _words(*values: str) -> str:
    return " ".join(re.sub(r"[_\-.]+", " ", value) for value in values if value)


def _stripped(name: str) -> str:
    """The object a kind list names: 信号灯类型 -> 信号灯, Vehicle type -> Vehicle."""
    cleaned = re.sub(r"\s+", " ", CATEGORY_WORDS.sub(" ", name)).strip(" -_")
    return cleaned or name


REASONS = {
    "none": ("没有代码表", "no code list"),
    "boolean": ("取值只有是/否", "yes/no values"),
    "state": ("名称含「{word}」, 表示状态或属性", "name says a state or property ({word})"),
    "kind": ("名称含「{word}」, 表示类别", "name says a kind ({word})"),
    "default": ("条目是物体名称, 名称不表示状态", "entries name things, not a state"),
}


def _decision(field: FieldStandard | None, listing: CodeList | None) -> tuple[Decision, str, str]:
    """Category or attribute, the reason key and the word that decided it."""
    names = _words(
        field.code if field else "",
        field.name_zh if field else "",
        field.name_en if field else "",
        listing.code if listing else "",
        listing.name if listing else "",
    )
    if listing is None:
        return "attribute", "none", ""
    values = {str(entry.value).casefold() for entry in listing.entries}
    values |= {entry.label_zh for entry in listing.entries}
    if values and values <= BOOLEAN_VALUES | {"0", "1"}:
        return "attribute", "boolean", ""
    if state := STATE_WORDS.search(names):
        return "attribute", "state", state.group(0).strip()
    if kind := CATEGORY_WORDS.search(names):
        return "category", "kind", kind.group(0).strip()
    return "category", "default", ""


def _reason(key: str, word: str, *, zh: bool) -> str:
    return REASONS[key][0 if zh else 1].format(word=word)


def _subtree(field: FieldStandard | None, listing: CodeList) -> tuple[str, list[CategorySource]]:
    root = field.code if field else listing.code
    name_zh = _stripped(field.name_zh if field else listing.name)
    name_en = (
        _stripped(field.name_en) if field else (listing.name if listing.name.isascii() else "")
    )
    parent = CategorySource(
        key=root,
        name_zh=name_zh,
        name_en=_stripped(name_en) if name_en else "",
        description=field.description if field else "",
    )
    children = [
        CategorySource(
            key=f"{root}.{entry.value}",
            name_zh=entry.label_zh,
            name_en=entry.label_en,
            parent_key=root,
        )
        for entry in listing.entries
    ]
    return root, [parent, *children]


def _scope(name_zh: str, name_en: str, roots: dict[str, CategorySource]) -> str | None:
    """Attach a property to the subtree it names (信号灯颜色 -> 信号灯), else to all labels."""
    for key, root in roots.items():
        if (root.name_zh and name_zh.startswith(root.name_zh)) or (
            root.name_en and name_en.casefold().startswith(root.name_en.casefold())
        ):
            return key
    return None


def _note(code: str, name: str, decision: Decision, reason: str, result: str, *, zh: bool) -> str:
    if zh:
        kind = "物体类别" if decision == "category" else "状态/属性"
        return f"「{name}」({code}): {reason}, 判为{kind} → {result}"
    kind = "object kinds" if decision == "category" else "a state or property"
    return f"{name} ({code}): {reason}; treated as {kind} -> {result}"


def classify_standards(
    contract: StandardsContract, codes: tuple[str, ...], language: str
) -> StandardSources:
    """Split the named standard codes into label subtrees and attributes, with reasons."""
    fields = {item.code: item for item in contract.standards}
    lists = {item.code: item for item in contract.code_lists}
    categories: list[CategorySource] = []
    roots: dict[str, CategorySource] = {}
    pending: list[tuple[str, FieldStandard, CodeList | None, str]] = []
    notes: list[str] = []
    used: set[str] = set()
    zh = language == "zh"
    for code in codes:
        field = fields.get(code)
        listing = lists.get(field.code_list or "") if field else lists.get(code)
        if field is None and listing is None:
            message = f"Unknown data standard code: {code}"
            raise ValidationError(message)
        if listing is not None and listing.code in used:
            continue
        decision, key, word = _decision(field, listing)
        reason = _reason(key, word, zh=zh)
        name = (
            (field.name_zh if zh else field.name_en) if field else listing.name if listing else code
        )
        if decision == "category" and listing is not None:
            used.add(listing.code)
            root, subtree = _subtree(field, listing)
            categories += subtree
            roots[root] = subtree[0]
            result = (
                f"标签「{subtree[0].name_zh}」及 {len(subtree) - 1} 个子标签"
                if zh
                else f"label {subtree[0].name_en or subtree[0].name_zh} with "
                f"{len(subtree) - 1} child labels"
            )
            notes.append(_note(code, name, decision, reason, result, zh=zh))
        elif field is not None:
            pending.append((code, field, listing, reason))
    attributes, attribute_notes = _attributes(pending, roots, zh=zh)
    return StandardSources(
        categories=tuple(categories),
        attributes=tuple(attributes),
        notes=(*notes, *attribute_notes),
    )


def _attributes(
    pending: list[tuple[str, FieldStandard, CodeList | None, str]],
    roots: dict[str, CategorySource],
    *,
    zh: bool,
) -> tuple[list[AttributeSource], list[str]]:
    attributes: list[AttributeSource] = []
    notes: list[str] = []
    for code, field, listing, reason in pending:
        scope = _scope(field.name_zh, field.name_en, roots)
        options = (
            tuple((str(e.value), e.label_zh, e.label_en) for e in listing.entries)
            if listing
            else ()
        )
        attributes.append(
            AttributeSource(
                key=field.code,
                name_zh=field.name_zh,
                name_en=field.name_en,
                data_type=field.data_type,
                options=options,
                required=field.required,
                scope=scope,
            )
        )
        target = roots[scope].name_zh if scope else ("全部标签" if zh else "every label")
        result = f"属性, 挂在「{target}」" if zh else f"attribute on {target}"
        name = field.name_zh if zh else field.name_en
        notes.append(_note(code, name, "attribute", reason, result, zh=zh))
    return attributes, notes
