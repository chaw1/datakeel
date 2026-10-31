# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Plain words for the fixed choices parameters and read results carry.

A card, a question or an answer says 「按技能派」 or 「打回」, never ``skill`` or ``rework``.
English keeps the words where they already read as English.
"""

from datakeel.intents.field_names import ENUM_LABELS
from datakeel.intents.wording import field_label

__all__ = ["ENUM_LABELS", "enum_label", "key_label"]


def enum_label(value: str, language: str) -> str:
    """A fixed choice in words; values without a label are returned as they are."""
    zh, en = ENUM_LABELS.get(value, (value, value))
    return zh if language == "zh" else en


def key_label(key: str, language: str) -> str:
    """A read result's key as a person would say it."""
    label = field_label(key, language)
    if label == key and key in ENUM_LABELS:
        return enum_label(key, language)  # a key named after a choice: classification
    return label.replace("_", " ") if label == key else label
