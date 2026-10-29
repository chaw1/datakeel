# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Maintain meaningful short measurement labels and bilingual count-table keys."""

import re
from itertools import product
from typing import cast, get_args

from datakeel.core.evidence_models import AssertionStatus, Verification
from datakeel.datasheets.vocabulary import ENGLISH_GRAMMAR, EVIDENCE_STATE_LABELS, field_label

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
_MODALITY_ALIASES = (
    ("image", "images", "图片", "图像"),
    ("audio", "音频"),
    ("text", "texts", "文本"),
    ("video", "videos", "视频"),
)
_STATE_KEYS: tuple[AssertionStatus | Verification, ...] = (
    *cast("tuple[AssertionStatus, ...]", get_args(AssertionStatus)),
    *cast("tuple[Verification, ...]", get_args(Verification)),
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


def _word_root(word: str) -> str:
    return word.removesuffix("s") if not word.endswith("ss") else word


def _english_variants(label: str) -> tuple[str, ...]:
    forms = (
        tuple(sorted(word for word in ENGLISH_GRAMMAR if _word_root(word) == _word_root(token)))
        or (token,)
        for token in label.split()
    )
    return tuple(" ".join(words) for words in product(*forms))


def _state_labels(key: AssertionStatus | Verification) -> tuple[str, ...]:
    chinese, english = EVIDENCE_STATE_LABELS[key]
    return tuple(
        dict.fromkeys(
            (
                key,
                key.replace("_", " "),
                *_english_variants(english),
                chinese,
                chinese.removeprefix("已"),
            )
        )
    )


def key_labels(key: str) -> tuple[str, ...]:
    """Derive product-state names from typed keys and their presentation vocabulary."""
    for state in _STATE_KEYS:
        if key.casefold() == state:
            return _state_labels(state)
    return next((group for group in _MODALITY_ALIASES if key.casefold() in group), (key,))


def state_predicate(text: str) -> bool:
    """Recognize a whole state predicate after its counted object, including optional still."""
    phrase = text.removeprefix("still ")
    return any(phrase in _state_labels(state) for state in _STATE_KEYS)


def modality_key(context: str, *, before: bool) -> str | None:
    """Use the nearest stated modality rather than a later, contradictory modifier."""
    mentions = [
        (match.start(), group[0])
        for group in _MODALITY_ALIASES
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
