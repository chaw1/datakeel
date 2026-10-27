# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recognize written cardinal numbers before lexical evidence matching."""

import re
from decimal import Decimal

_TEN = 10
_FIRST_TENS = 20
_SECTION_SCALE = 10000

_ENGLISH_SMALL = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_ENGLISH_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000}
_ENGLISH_TOKEN = "(?:" + "|".join((*_ENGLISH_SMALL, *_ENGLISH_SCALES)) + ")"
_ENGLISH = re.compile(
    r"\b" + _ENGLISH_TOKEN + r"(?:[-\s]+(?:and[-\s]+)?" + _ENGLISH_TOKEN + r")*\b",
    re.IGNORECASE,
)
_CHINESE_DIGITS = {
    "零": 0,
    "\u3007": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_SCALES = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
_CHINESE = re.compile("[" + "".join((*_CHINESE_DIGITS, *_CHINESE_SCALES)) + "]+")


def _english_value(text: str) -> Decimal:
    total, current, previous = 0, 0, 0
    for word in text.casefold().replace("-", " ").split():
        if word == "and":
            continue
        if word in _ENGLISH_SMALL:
            value = _ENGLISH_SMALL[word]
            if previous and not (previous >= _FIRST_TENS and previous % _TEN == 0 and value < _TEN):
                return Decimal("NaN")
            current += value
            previous = value
        elif word == "hundred":
            current = (current or 1) * 100
            previous = 0
        else:
            total += (current or 1) * _ENGLISH_SCALES[word]
            current, previous = 0, 0
    return Decimal(total + current)


def _chinese_value(text: str) -> Decimal:
    if not any(char in _CHINESE_SCALES for char in text):
        return Decimal("".join(str(_CHINESE_DIGITS[char]) for char in text))
    total, section, current = 0, 0, 0
    for char in text:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
            continue
        scale = _CHINESE_SCALES[char]
        if scale < _SECTION_SCALE:
            section += (current or 1) * scale
        else:
            total += (section + current or 1) * scale
            section = 0
        current = 0
    return Decimal(total + section + current)


def written_numbers(text: str) -> set[Decimal]:
    """Return Arabic-equivalent values for English and Chinese written cardinal spans."""
    english = {_english_value(match.group()) for match in _ENGLISH.finditer(text)}
    return english | {_chinese_value(match.group()) for match in _CHINESE.finditer(text)}


def erase_written_numbers(text: str) -> str:
    """Remove separately validated cardinal spans before testing names and content words."""
    text = _ENGLISH.sub(" ", text)

    def replacement(match: re.Match[str]) -> str:
        if match.group() == text.strip():
            return " "
        after = text[match.end() :]
        before = text[: match.start()]
        classifier = re.match(r"(?:组(?!织)|名(?!称|字)|[个份条张件次人项幅篇套台本种])", after)
        quantity = re.search(
            r"(?:数量|总数|总分|总计|共计|共有|共|包含|包括|计数|为|是)\s*$", before
        )
        quoted = before.endswith(('"', "“", "「", "『")) and after.startswith(
            ('"', "”", "」", "』")
        )
        return " " if classifier or quantity or quoted else match.group()

    return _CHINESE.sub(replacement, text)
