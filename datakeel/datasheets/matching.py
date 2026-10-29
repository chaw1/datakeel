# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conservative Unicode, number, date, and content-token evidence matching."""

import re
import unicodedata
from collections.abc import Iterable

from datakeel.core.datasheet_models import DatasheetFact
from datakeel.datasheets.names import names_supported
from datakeel.datasheets.number_words import erase_written_numbers
from datakeel.datasheets.numeric import (
    erase_dates,
    fact_readings,
    normalized,
    numeric_issues,
    value_strings,
)
from datakeel.datasheets.sentences import split_sentences
from datakeel.datasheets.units import NUMBER
from datakeel.datasheets.vocabulary import (
    CHINESE_GRAMMAR,
    ENGLISH_GRAMMAR,
    field_label,
    kind_label,
    unit_label,
)

_LATIN = re.compile(r"[^\W\d_][\w'\u2019-]*", re.UNICODE)
_HAN = re.compile(r"[\u3400-\u9fff]+")

__all__ = [
    "atomic_sentences",
    "fact_readings",
    "normalized",
    "numeric_issues",
    "stable_unique",
    "term_issues",
    "value_strings",
]


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
    text = erase_written_numbers(erase_dates(normalized(text)))

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
        for word in _words(erase_written_numbers(NUMBER.sub(" ", erase_dates(part))))
    }
    # Dates/numbers have their own stricter matcher and must not become lexical exceptions.
    lexical = erase_written_numbers(NUMBER.sub(" ", erase_dates(normalized(text))))
    unknown = set(_words(lexical)) - known_words - ENGLISH_GRAMMAR
    if (
        unknown
        or not _proper_phrases(erase_written_numbers(NUMBER.sub(" ", erase_dates(text))), evidence)
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
