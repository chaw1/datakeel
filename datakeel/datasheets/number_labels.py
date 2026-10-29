# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Maintain meaningful short measurement labels and bilingual count-table keys."""

import re

from datakeel.datasheets.vocabulary import field_label

_ALIASES = {
    "manifest.file_count": (
        "files",
        "file total",
        "total files",
        "number of files",
        "文件数",
        "文件总数",
    ),
    "assertions.count": (
        "assertions",
        "assertion count",
        "assertion total",
        "total assertions",
        "number of assertions",
        "断言数",
        "断言总数",
        "证据断言数",
    ),
    "kg.relation_count": (
        "relations",
        "relation count",
        "relation total",
        "total relations",
        "number of relations",
        "关系数",
        "关系总数",
        "图谱关系数",
    ),
    "quality.total": ("quality total", "quality rating", "质量分数", "质量得分", "质量评分"),
    "compliance.total": (
        "compliance total",
        "compliance rating",
        "合规分数",
        "合规得分",
        "合规评分",
    ),
}
_KEY_ALIASES = (
    ("image", "images", "图片", "图像"),
    ("audio", "音频"),
    ("text", "texts", "文本"),
    ("video", "videos", "视频"),
    ("accepted", "接受", "已接受"),
    ("rejected", "拒绝", "已拒绝"),
    ("pending", "待审阅", "待审核"),
    ("verified", "已核对"),
)
_HAN = re.compile(r"[\u3400-\u9fff]")
_CLAUSE = re.compile(
    r"[,;!?、\uff0c。\uff1b\uff01\uff1f]|\b(?:and|or|but|while|plus)\b|以及|和|与|及"
)


def number_labels(field: str) -> tuple[str, ...]:
    """Accept display labels and concise forms that retain the measurement's identity."""
    suffix = field.rsplit(".", 1)[-1]
    return (
        field,
        suffix if "_" in suffix else "",
        suffix.replace("_", " ") if "_" in suffix else "",
        field_label(field, "en"),
        field_label(field, "zh"),
        *_ALIASES.get(field, ()),
    )


def key_labels(key: str) -> tuple[str, ...]:
    """Keep each record key's value attached to that key across common language forms."""
    return next((group for group in _KEY_ALIASES if key.casefold() in group), (key,))


def modality_key(context: str, *, before: bool) -> str | None:
    """Use the nearest stated modality rather than a later, contradictory modifier."""
    mentions = [
        (match.start(), group[0])
        for group in _KEY_ALIASES[:4]
        for label in group
        for match in re.finditer(
            re.escape(label) if _HAN.search(label) else r"\b" + re.escape(label) + r"\b", context
        )
    ]
    if not mentions:
        return None
    return (max(mentions) if before else min(mentions))[1]


def has_label(context: str, labels: tuple[str, ...]) -> bool:
    """Match complete Latin labels and contiguous Chinese labels without merging words."""
    return any(
        label in context
        if _HAN.search(label)
        else re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", context) is not None
        for label in labels
        if label
    )


def number_context(before: str, after: str) -> tuple[str, str]:
    """Limit each side to its own clause so a previous predicate cannot name the next value."""
    return _CLAUSE.split(before)[-1], _CLAUSE.split(after)[0]
