# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Split narrative sentences while preserving quoted data and name abbreviations."""

import re

_QUOTES = {'"': '"', "“": "”", "「": "」", "『": "』", "\u2018": "\u2019"}
_ABBREVIATION = re.compile(
    r"(?:\b(?:dr|mr|mrs|ms|prof|sr|jr|st|vs|etc|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)|e\.g|i\.e)$",
    re.IGNORECASE,
)
_INITIAL = re.compile(r"\b[A-Z]$")


def _opening_quote(text: str, index: int) -> str:
    char = text[index]
    if char == "'" and (index == 0 or not text[index - 1].isalnum()):
        return "'"
    return _QUOTES.get(char, "")


def _boundary(text: str, index: int) -> bool:
    char = text[index]
    if char in "。\uff01\uff1f!?":
        return True
    if char != ".":
        return False
    if index + 1 < len(text) and not text[index + 1].isspace():
        return False
    prefix = text[:index]
    return not (_ABBREVIATION.search(prefix) or _INITIAL.search(prefix))


def _advance_quote(char: str, quote: str, *, escaped: bool) -> tuple[str, bool]:
    if escaped:
        return quote, False
    if char == "\\":
        return quote, True
    return ("", False) if char == quote else (quote, False)


def split_sentences(text: str) -> tuple[str, ...]:
    """Keep quoted JSON, nested brackets, abbreviations and punctuation intact."""
    parts: list[str] = []
    quote, depth, start, escaped = "", 0, 0, False
    for index, char in enumerate(text):
        if quote:
            quote, escaped = _advance_quote(char, quote, escaped=escaped)
            continue
        quote = _opening_quote(text, index)
        if quote:
            continue
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth = max(0, depth - 1)
        elif depth == 0 and _boundary(text, index):
            if part := text[start : index + 1].strip():
                parts.append(part)
            start = index + 1
    if part := text[start:].strip():
        parts.append(part)
    return tuple(parts)
