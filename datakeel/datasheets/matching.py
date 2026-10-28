# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conservative Unicode, number, date, and content-token evidence matching."""

import re
import unicodedata
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact
from datakeel.datasheets.names import names_supported
from datakeel.datasheets.number_words import erase_written_numbers
from datakeel.datasheets.sentences import split_sentences
from datakeel.datasheets.units import NUMBER, Reading, supported, text_readings
from datakeel.datasheets.vocabulary import (
    CHINESE_GRAMMAR,
    ENGLISH_GRAMMAR,
    field_label,
    kind_label,
    unit_label,
)

# Chinese dates may space their 年/月/日 markers; numeric separators stay unspaced.
_DATE = re.compile(
    r"(?<!\d)(\d{4})(?:[-/.]|[ \t]*年[ \t]*)(\d{1,2})(?:[-/.]|[ \t]*月[ \t]*)(\d{1,2})"
    r"(?:[ \t]*日)?(?!\d)"
)
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            "jan january",
            "feb february",
            "mar march",
            "apr april",
            "may",
            "jun june",
            "jul july",
            "aug august",
            "sep sept september",
            "oct october",
            "nov november",
            "dec december",
        ),
        start=1,
    )
    for name in names.split()
}
_MONTH_PATTERN = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"
_NAMED_DATE = re.compile(r"\b(" + _MONTH_PATTERN + r")\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE)
_DAY_FIRST_DATE = re.compile(
    r"\b(\d{1,2})\s+(" + _MONTH_PATTERN + r")\.?\s+(\d{4})\b", re.IGNORECASE
)
# A timestamp's clock follows its date directly, as in 2026-10-27T15:55:01.
_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")
_LATIN = re.compile(r"[^\W\d_][\w'\u2019-]*", re.UNICODE)
_HAN = re.compile(r"[\u3400-\u9fff]+")


def normalized(value: str) -> str:
    """Normalize compatibility glyphs and case without conflating separate words."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"(?<=\d)\s+(?:percent|per cent)\b", "%", value)


def value_strings(value: JsonValue) -> tuple[str, ...]:
    """Flatten JSON leaves and keys while retaining complete entity strings."""
    if isinstance(value, dict):
        return tuple(value) + tuple(part for item in value.values() for part in value_strings(item))
    if isinstance(value, list):
        return tuple(part for item in value for part in value_strings(item))
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return (str(value).lower(),)
    return (str(value),)


def _date(value: re.Match[str]) -> str:
    try:
        return date(*(int(part) for part in value.groups())).isoformat()
    except ValueError:
        return value.group()


def _named_date(match: re.Match[str], *, day_first: bool) -> str:
    month, day, year = match.groups()
    if day_first:
        month, day = day, month
    try:
        return date(int(year), _MONTHS[month.casefold()], int(day)).isoformat()
    except ValueError:
        return match.group()


def _dates(text: str) -> set[str]:
    values = {_date(match) for match in _DATE.finditer(text)}
    values.update(_named_date(match, day_first=False) for match in _NAMED_DATE.finditer(text))
    values.update(_named_date(match, day_first=True) for match in _DAY_FIRST_DATE.finditer(text))
    return values


def _erase_dates(text: str) -> str:
    return _DAY_FIRST_DATE.sub(" ", _NAMED_DATE.sub(" ", _DATE.sub(" ", text)))


_MEASURED = {
    "count": "count",
    "ratio": "ratio",
    "percent": "percent",
    "score": "score",
    "bytes": "bytes",
    "duration": "duration",
    "date": "date",
}


def _measured(fact: DatasheetFact) -> str | None:
    if fact.kind == "amount":
        return f"amount:{fact.unit}" if fact.unit else None
    return _MEASURED.get(fact.kind)


def fact_readings(fact: DatasheetFact) -> frozenset[Reading]:
    """Type every recorded number by its fact kind, or by its own words in recorded text."""
    measured = _measured(fact)
    readings: set[Reading] = set()

    def visit(value: JsonValue) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float):
            readings.add((Decimal(str(value)), measured))
        elif isinstance(value, str):
            text = normalized(value)
            for match in (*_DATE.finditer(text), *_TIME.finditer(text)):
                readings.update((Decimal(part), "date") for part in match.groups() if part)
            for item, unit in text_readings(_erase_dates(text)):
                readings.add((item, unit if measured is None or unit == "percent" else measured))
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(key)
                visit(item)
        else:
            for item in value:
                visit(item)

    visit(fact.value)
    return frozenset(readings)


def _unsupported_numbers(text: str, evidence: frozenset[Reading]) -> bool:
    return not all(supported(item, evidence) for item in text_readings(_erase_dates(text)))


def numeric_issues(text: str, facts: tuple[DatasheetFact, ...]) -> tuple[str, ...]:
    """Require dates, and numbers under the same unit, in cited values, never in fact IDs."""
    candidates = tuple(normalized(part) for fact in facts for part in value_strings(fact.value))
    dates = {item for part in candidates for item in _dates(part)}
    dates.update(fact.recorded_at.date().isoformat() for fact in facts)
    numbers = frozenset(item for fact in facts for item in fact_readings(fact))
    issues: list[str] = []
    if _dates(normalized(text)) - dates:
        issues.append("unsupported_date")
    if _unsupported_numbers(normalized(text), numbers):
        issues.append("unsupported_number")
    return tuple(issues)


def _words(text: str) -> tuple[str, ...]:
    return tuple(match.group() for match in _LATIN.finditer(_HAN.sub(" ", text)))


def _han_supported(run: str, evidence: tuple[str, ...]) -> bool:
    # Adjacent evidence fragments cannot synthesize a new name from separate facts.
    if any(run in part for part in evidence):
        return True
    possible: set[tuple[int, bool]] = {(0, False)}
    for start in range(len(run)):
        if not any(pos == start for pos, _ in possible):
            continue
        for end in range(start + 1, len(run) + 1):
            fragment = run[start:end]
            if fragment in CHINESE_GRAMMAR and any(pos == start for pos, _ in possible):
                possible.add((end, False))
            if (start, False) not in possible:
                continue
            in_fact = any(fragment in part for part in evidence)
            if in_fact and (len(fragment) > 1 or fragment in evidence):
                possible.add((end, True))
    return any(pos == len(run) for pos, _ in possible)


def _proper_phrases(text: str, evidence: tuple[str, ...]) -> bool:
    # Preserve capitalization for multi-word names; sentence-initial grammar is harmless.
    pattern = r"(?<!\w)[A-Z][\w'-]*(?:[ \t]+(?:(?:of|the|and)[ \t]+)?[A-Z][\w'-]*)*"
    for match in re.finditer(pattern, unicodedata.normalize("NFKC", text)):
        words = normalized(match.group()).split()
        starters = {
            "the",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "their",
            "they",
            "there",
            "a",
            "an",
        }
        if (
            match.start() == 0
            and words
            and ((len(words) == 1 and words[0] in ENGLISH_GRAMMAR) or words[0] in starters)
        ):
            words.pop(0)
        if not words:
            continue
        phrase = " ".join(words)
        if not any(phrase in part for part in evidence):
            names = re.split(r"\s+and\s+", phrase)
            if len(names) == 1 or not all(any(name in part for part in evidence) for name in names):
                return False
    return True


def _content_phrases(text: str, evidence: tuple[str, ...]) -> bool:
    # Adjacent recorded name tokens must occur together, even when the model lowercases them.
    # Chinese text between Latin terms (和, 与, 包括) separates them like punctuation does.
    for group in re.findall(r"[\w'-]+(?:[ \t]+[\w'-]+)*", _HAN.sub("\n", text)):
        phrase: list[str] = []
        for word in (*_words(group), "and"):
            if word not in ENGLISH_GRAMMAR:
                phrase.append(word)
                continue
            if phrase and not any(" ".join(phrase) in part for part in evidence):
                return False
            phrase = []
    return True


def _phrase_text(text: str) -> str:
    text = erase_written_numbers(_erase_dates(normalized(text)))

    def replacement(match: re.Match[str]) -> str:
        if re.search(r"[A-Za-z][A-Za-z0-9_-]*-$", text[: match.start()]):
            return match.group()
        return " "

    return NUMBER.sub(replacement, text)


def term_issues(text: str, facts: tuple[DatasheetFact, ...]) -> tuple[str, ...]:
    """Refuse unsupported content words, including previously unseen proper names."""
    values = tuple(normalized(part) for fact in facts for part in value_strings(fact.value))
    fields = tuple(normalized(fact.field) for fact in facts)
    labels = tuple(
        normalized(label)
        for fact in facts
        for language in ("zh", "en")
        for label in (
            field_label(fact.field, language),
            unit_label(fact.unit, language),
            kind_label(fact.kind, language),
        )
        if label is not None
    )
    evidence = values + fields + labels
    known_words = {
        word
        for part in evidence
        for word in _words(erase_written_numbers(NUMBER.sub(" ", _erase_dates(part))))
    }
    # Dates/numbers have their own stricter matcher and must not become lexical exceptions.
    lexical = erase_written_numbers(NUMBER.sub(" ", _erase_dates(normalized(text))))
    unknown = set(_words(lexical)) - known_words - ENGLISH_GRAMMAR
    if (
        unknown
        or not _proper_phrases(erase_written_numbers(NUMBER.sub(" ", _erase_dates(text))), evidence)
        or not names_supported(text, facts)
        or not _content_phrases(_phrase_text(text), evidence)
        or any(not _han_supported(run, evidence) for run in _HAN.findall(lexical))
    ):
        return ("unsupported_term",)
    return ()


def atomic_sentences(text: str) -> tuple[str, ...]:
    """Split narrative assertions without dividing quoted JSON or name abbreviations."""
    return split_sentences(text)


def stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    """Remove duplicate references while preserving the generated citation order."""
    return tuple(dict.fromkeys(values))
