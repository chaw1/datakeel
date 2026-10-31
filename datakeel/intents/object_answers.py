# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A list of platform objects read aloud: how many, their names, states and people.

Object identities, content digests and asset types stay in the data; the sentence says
「找到 4 个任务: 进行中 2, 已提交 2; 涉及的人: liuyang。」
"""

from collections import Counter

from pydantic import JsonValue

from datakeel.intents.plain_words import enum_label

KIND_WORDS = {
    "production_task": ("任务", "tasks"),
    "task_package": ("任务包", "packages"),
    "project": ("项目", "projects"),
    "assignment": ("指派", "assignments"),
    "annotation_revision": ("标注版本", "annotation revisions"),
    "review": ("审核记录", "reviews"),
    "label_set": ("标签集", "label sets"),
    "template": ("模板", "templates"),
    "model": ("模型", "models"),
    "prelabel_run": ("预标注运行", "pre-label runs"),
    "role": ("角色", "roles"),
}
NAME_KEYS = ("name", "display_name", "filename")
PEOPLE_KEYS = ("annotator_id", "actor", "reviewer_id")
LIMIT = 10


def _properties(data: list[JsonValue]) -> tuple[str, list[dict[str, JsonValue]]]:
    kinds: set[str] = set()
    found: list[dict[str, JsonValue]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        reference, properties = item.get("asset_ref"), item.get("properties")
        if isinstance(reference, dict) and isinstance(reference.get("asset_type"), str):
            kinds.add(str(reference.get("asset_type")))
        if isinstance(properties, dict):
            found.append(properties)
    return (kinds.pop() if len(kinds) == 1 else ""), found


def _words(values: list[dict[str, JsonValue]], keys: tuple[str, ...]) -> list[str]:
    seen = (str(item[key]) for item in values for key in keys if isinstance(item.get(key), str))
    return list(dict.fromkeys(seen))


def objects_text(data: JsonValue, language: str) -> str | None:
    """One sentence for a production_objects read; None when the data is not such a list."""
    if not isinstance(data, list):
        return None
    kind, values = _properties(data)
    zh = language == "zh"
    word = KIND_WORDS.get(kind, ("对象", "objects"))[0 if zh else 1]
    if not values:
        return "没有找到符合条件的对象。" if zh else "Nothing matches."
    states = Counter(
        enum_label(str(item["state"]), language)
        for item in values
        if isinstance(item.get("state"), str)
    )
    names, people = _words(values, NAME_KEYS)[:LIMIT], _words(values, PEOPLE_KEYS)[:LIMIT]
    parts = [f"找到 {len(values)} 个{word}" if zh else f"Found {len(values)} {word}"]
    separator = "、" if zh else ", "
    if names:
        parts.append(separator.join(names))
    if states:
        listed = ", ".join(f"{state} {count}" for state, count in states.most_common())
        parts.append(f"状态: {listed}" if zh else f"states: {listed}")
    if people:
        parts.append(("涉及的人: " if zh else "people: ") + separator.join(people))
    return "; ".join(parts) + ("。" if zh else ".")
