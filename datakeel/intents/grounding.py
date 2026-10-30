# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Accept a container identity only when the person or the page actually named it.

A model may copy the only project in the catalog into a plan although the sentence never
mentioned a project. For writes that is a guess, so such a value is turned back into a
question. A value is grounded when it equals the page context or the previous turn's
object, or when its name or id appears in the person's words.
"""

import re

from datakeel.intents.catalog import CatalogEntry

GROUNDED_FIELDS = frozenset({"dataset_id", "project_id", "package_id", "label_set_id"})
_GENERIC_ZH = frozenset({"项目", "任务", "数据", "标签", "图片", "版本", "标注", "生产", "数据集"})
_GENERIC_EN = frozenset(
    {"project", "task", "tasks", "dataset", "data", "package", "label", "labels", "set", "the"}
)
_WORD = re.compile(r"[a-z0-9]{3,}")
_HAN = re.compile(r"[一-鿿]+")


def mentioned(entry: CatalogEntry, text: str) -> bool:
    """True when the sentence contains the object's id, a name, or a distinctive part of it."""
    spoken = text.casefold()
    names = [entry.id, entry.label, *entry.names]
    if any(name and name.casefold() in spoken for name in names):
        return True
    words = set(_WORD.findall(spoken)) - _GENERIC_EN
    for name in names:
        folded = name.casefold()
        if words & (set(_WORD.findall(folded)) - _GENERIC_EN):
            return True
        for run in _HAN.findall(folded):
            pairs = {run[index : index + 2] for index in range(len(run) - 1)} - _GENERIC_ZH
            if any(pair in spoken for pair in pairs):
                return True
    return False


def grounded(field: str, entry: CatalogEntry | None, text: str, page_value: str | None) -> bool:
    """Whether a resolved container identity came from the page, the last turn or the words."""
    if field not in GROUNDED_FIELDS or not text or entry is None:
        return True
    return entry.id == page_value or mentioned(entry, text)
