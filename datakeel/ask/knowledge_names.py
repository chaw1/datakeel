# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize registered names without treating relationship words as subject boundaries."""

import re
import unicodedata

from datakeel.core.knowledge_models import KnowledgeSubject
from datakeel.core.models import BoundaryModel

_CJK = r"\u3400-\u9fff"
_MIN_NAME_LENGTH = 2
_GENERIC = frozenset(
    {"表", "人", "组", "数据", "指标", "团队", "table", "metric", "data", "team", "owner"}
)


class SubjectName(BoundaryModel):
    """Bind one registered spelling to its exact catalog or document identity."""

    name: str
    subject: KnowledgeSubject
    rank: int = 0


class SubjectMention(BoundaryModel):
    """Retain one nonoverlapping normalized span and all indistinguishable identities."""

    start: int
    end: int
    text: str
    candidates: tuple[KnowledgeSubject, ...]


def normalize_name(text: str) -> str:
    """Apply NFKC, case folding, and spacing equivalence at Chinese/Latin boundaries."""
    text = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    text = re.sub(rf"(?<=[{_CJK}])\s+(?=[A-Za-z0-9])", "", text)
    return re.sub(rf"(?<=[A-Za-z0-9])\s+(?=[{_CJK}])", "", text)


def name_variants(name: str) -> tuple[str, ...]:
    """Allow a trailing table descriptor to be omitted without cutting ordinary words."""
    name = normalize_name(name)
    short = re.sub(r"(?:表|\s+table)$", "", name).strip()
    return tuple(dict.fromkeys(value for value in (name, short) if value))


def name_occurrences(text: str, name: str) -> tuple[tuple[int, int], ...]:
    """Protect short generic labels and complete Latin identifiers during matching."""
    if len(name) < _MIN_NAME_LENGTH or name in _GENERIC:
        return ()
    pattern = re.escape(name)
    if name[0].isascii() and name[0].isalnum():
        pattern = r"(?<![A-Za-z0-9_])(?<![A-Za-z0-9_][./])" + pattern
    if name[-1].isascii() and name[-1].isalnum():
        pattern += r"(?![A-Za-z0-9_]|[./][A-Za-z0-9_])"
    return tuple((hit.start(), hit.end()) for hit in re.finditer(pattern, text))
