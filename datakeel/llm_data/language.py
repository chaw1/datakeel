# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Estimate script-based language and tokenizer-free text length offline."""

import re
from typing import Literal

Language = Literal["zh", "en", "mixed", "unknown"]
_CJK = re.compile(r"[\u3400-\u9fff\U00020000-\U0002ffff]")
_LATIN = re.compile(r"[a-zA-Z]")
_WORDS = re.compile(r"[a-zA-Z]+")
_COMMON = frozenset(
    [
        "the",
        "a",
        "an",
        "is",
        "are",
        "this",
        "that",
        "to",
        "of",
        "and",
        "in",
        "for",
        "with",
        "you",
        "it",
        "please",
        "explain",
        "how",
        "what",
    ]
)

_MIN_CHINESE = 4
_MIN_LATIN = 8
_MIN_MIX_RATIO = 0.12
_MAX_MIX_RATIO = 0.85
_MIN_WORDS = 2
_CHINESE_MAJORITY = 0.5
_LATIN_SCRIPT_RATIO = 0.8


def identify_language(text: str) -> tuple[Language, float]:
    """Classify Chinese, English or mixed scripts, exposing uncertainty for short inputs."""
    chinese = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    total = chinese + latin
    if not total:
        return "unknown", 0.0
    words = _WORDS.findall(text.casefold())
    common = sum(word in _COMMON for word in words)
    ratio = chinese / total
    if (
        chinese >= _MIN_CHINESE
        and latin >= _MIN_LATIN
        and _MIN_MIX_RATIO <= ratio <= _MAX_MIX_RATIO
        and len(words) >= _MIN_WORDS
    ):
        return "mixed", round(min(0.99, 0.65 + min(ratio, 1 - ratio) / 2 + total / 1000), 3)
    if ratio >= _CHINESE_MAJORITY:
        return "zh", round(min(0.99, 0.55 + ratio * 0.4 + total / 1000), 3)
    if latin / max(1, sum(char.isalpha() for char in text)) >= _LATIN_SCRIPT_RATIO:
        return "en", round(min(0.99, 0.6 + common / max(1, len(words)) / 4 + total / 500), 3)
    return "unknown", round(latin / total / 2, 3)


def estimate_tokens(text: str) -> int:
    """Count CJK characters and approximate other UTF-8 text without a tokenizer dependency."""
    chinese = len(_CJK.findall(text))
    other = _CJK.sub("", text)
    return chinese + (len(other.encode("utf-8")) + 3) // 4
