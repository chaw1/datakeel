# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic first pass: rank registry entries by their declared phrases and examples."""

import re
from functools import lru_cache

from pydantic import Field

from datakeel.actions.registry import action_definitions
from datakeel.core.models import BoundaryModel
from datakeel.ontology.models import OntologyRegistry
from datakeel.ontology.registry import registry

_WORD = re.compile(r"[a-z][a-z0-9_]+")
_CJK = re.compile(r"[一-鿿]+")
_STOP = frozenset(
    {
        "the",
        "this",
        "these",
        "that",
        "with",
        "and",
        "for",
        "from",
        "into",
        "all",
        "my",
        "to",
        "of",
        "on",
        "in",
        "it",
        "by",
        "an",
        "is",
        "are",
        "be",
        "me",
        "please",
    }
)
_ZH_STOP = frozenset(
    {"这个", "这些", "一个", "把这", "给我", "帮我", "我的", "所有", "的任", "务派"}
)
QUESTION = re.compile(
    r"[?\uff1f]|吗|谁|哪(个|些|位|一)|多少|几(个|条|张|次|人)|是否|怎么样|有没有|如何|"
    r"\b(who|which|what|how many|how much|whether|is there|are there|does|show me|list)\b",
    re.IGNORECASE,
)
RANK_LIMIT = 12


@lru_cache(maxsize=1)
def full_registry() -> OntologyRegistry:
    """Every controlled action and read function with its phrases and examples."""
    return registry(action_definitions())


class RankedEntry(BoundaryModel):
    """One action or read function with its lexical evidence score."""

    name: str
    kind: str
    score: float = Field(ge=0)


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> set[str]:
    """English stems plus Chinese character bigrams; stop words carry no evidence."""
    lowered = text.casefold().replace("_", " ")
    words = {_stem(word) for word in _WORD.findall(lowered) if word not in _STOP}
    grams = {
        run[index : index + 2]
        for run in _CJK.findall(lowered)
        for index in range(max(1, len(run) - 1))
    }
    return words | {gram for gram in grams if gram not in _ZH_STOP}


def _overlap(text: set[str], phrase: str) -> float:
    wanted = tokens(phrase)
    return len(text & wanted) / len(wanted) if wanted else 0


def rank(text: str, registry: OntologyRegistry) -> list[RankedEntry]:
    """Score every registered action and read function against one sentence."""
    words = tokens(text)
    entries = [(item.id, "action", item.phrases, item.examples) for item in registry.actions] + [
        (item.id, "function", item.phrases, item.examples) for item in registry.functions
    ]
    ranked: list[RankedEntry] = []
    for name, kind, phrases, examples in entries:
        phrase = max(
            (_overlap(words, value) for group in phrases.values() for value in group), default=0
        )
        example = max(
            (_overlap(words, value) for group in examples.values() for value in group), default=0
        )
        identity = _overlap(words, name.replace("_", " "))
        score = 2 * phrase + example + identity
        if kind == "function" and QUESTION.search(text):
            score += 0.5 * (phrase + identity)
        ranked.append(RankedEntry(name=name, kind=kind, score=round(score, 4)))
    ranked.sort(key=lambda item: (-item.score, item.name))
    return ranked


def is_question(text: str) -> bool:
    """Questions ask for information; they are answered by read functions, not plans."""
    return bool(QUESTION.search(text))
