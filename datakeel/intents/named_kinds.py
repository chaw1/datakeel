# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What a new object's own name already says, so it is never asked.

"夜间行人框选" is a box skill; "rain-poly-v2" is a polygon model at version 2. Only words
that say the annotation type or the version outright count; nothing else is guessed.
"""

import re

from pydantic import JsonValue

KIND_WORDS: dict[str, tuple[str, ...]] = {
    "box": ("框选", "拉框", "画框", "检测框", "bbox", "box", "det"),
    "polygon": ("多边形", "分割", "poly", "polygon", "seg"),
    "keypoints": ("关键点", "keypoint", "pose"),
    "classification": ("分类", "classif", "cls"),
    "text_span": ("文本片段", "实体", "ner", "span"),
}
VERSION = re.compile(r"(?:^|[-_\s.])v(\d+(?:\.\d+)*)$", re.IGNORECASE)
# "集装箱类型第 2 版", "version 2 of the labels": a label set version said in words.
SAID_VERSION = re.compile(r"第\s*(\d+)\s*版|版本\s*(\d+)|\bversion\s*(\d+)", re.IGNORECASE)


def named_kinds(name: str) -> list[str]:
    """Annotation types a name says outright, in the registry's order."""
    words = re.split(r"[-_\s.]+", name.casefold())
    found: list[str] = []
    for kind, spoken in KIND_WORDS.items():
        latin = [word for word in spoken if word.isascii()]
        if any(word in name for word in spoken if not word.isascii()) or any(
            part.startswith(word) for part in words for word in latin
        ):
            found.append(kind)
    return found


def named_version(name: str) -> str | None:
    """The version a name ends with ("rain-poly-v2" is 2)."""
    found = VERSION.search(name.strip())
    return found.group(1) if found else None


def said_version(said: str | None) -> int | None:
    """The version number the person's words give ("第 2 版" is 2), if any."""
    found = SAID_VERSION.search(said or "")
    return int(next(group for group in found.groups() if group)) if found else None


def named_skill_type(params: dict[str, JsonValue]) -> None:
    """A new skill whose name says one annotation type has that type."""
    name = params.get("name")
    if params.get("annotation_type") or not isinstance(name, str):
        return
    kinds = named_kinds(name)
    if len(kinds) == 1:
        params["annotation_type"] = kinds[0]


def spoken_requirement(params: dict[str, JsonValue]) -> None:
    """A skill requirement's type said in words ("分类标注") is the registered type's name."""
    need = params.get("skill_requirement")
    said = need.get("annotation_type") if isinstance(need, dict) else None
    if not isinstance(need, dict) or not isinstance(said, str) or said in KIND_WORDS:
        return
    kinds = named_kinds(said)
    if len(kinds) == 1:
        need["annotation_type"] = kinds[0]


def named_model(record: dict[str, JsonValue], name: str) -> None:
    """What a model's name says outright ("rain-poly-v2") is never asked."""
    spoken, kinds = named_version(name), named_kinds(name)
    if spoken and not record.get("version"):
        record["version"] = spoken
    if kinds and not record.get("capabilities"):
        record["capabilities"] = list(kinds)
