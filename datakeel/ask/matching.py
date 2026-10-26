# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic registered phrase matching with original NFC character anchors."""

import re
import unicodedata

from datakeel.ask.models import MetricLexeme
from datakeel.core.ask_models import MatchEvidence
from datakeel.core.metric_models import MetricDefinition, SemanticLayer, TermDefinition

_MIN_PREFIX = 2
_PREFIX_END = r"(?=$|[?\uff1f。\uff0c,\uff01!\s]|是多少|多少|怎么样|如何|呢)"


def occurrences(question: str, phrase: str) -> list[re.Match[str]]:
    """Find a nonempty registered phrase without matching inside ASCII words."""
    phrase = unicodedata.normalize("NFC", phrase)
    if not phrase.strip():
        return []
    pattern = re.escape(phrase)
    if phrase[0].isascii() and phrase[0].isalnum():
        pattern = r"(?<![A-Za-z0-9_])" + pattern
    if phrase[-1].isascii() and phrase[-1].isalnum():
        pattern += r"(?![A-Za-z0-9_])"
    return list(re.finditer(pattern, question, re.IGNORECASE))


def metric_matches(question: str, layer: SemanticLayer) -> tuple[MatchEvidence, ...]:
    """Match registered names, normalized identifiers, then conservative name prefixes."""
    matches = [
        _evidence(hit, lexeme)
        for lexeme in _lexemes(layer)
        for hit in occurrences(question, lexeme.text)
    ]
    matched = {item.metric_id for item in matches}
    for metric in layer.metrics:
        if metric.id in matched:
            continue
        lexeme = MetricLexeme(
            text=metric.id,
            source=f"metric:{metric.id}.id:normalized",
            metric_id=metric.id,
            match_kind="normalized",
        )
        hits = list(re.finditer(_identifier_pattern(metric.id), question, re.IGNORECASE))
        if hits:
            matches.extend(_evidence(hit, lexeme) for hit in hits)
            continue
        name = unicodedata.normalize("NFC", metric.name)
        for length in range(len(name) - 1, max(_MIN_PREFIX, len(name) // 2) - 1, -1):
            pattern = re.escape(name[:length]) + _PREFIX_END
            hits = list(re.finditer(pattern, question, re.IGNORECASE))
            if hits:
                lexeme = MetricLexeme(
                    text=name[:length],
                    source=f"metric:{metric.id}.name:prefix",
                    metric_id=metric.id,
                    match_kind="prefix",
                )
                matches.extend(_evidence(hit, lexeme) for hit in hits)
                break
    return tuple(sorted(set(matches), key=lambda item: (item.start, item.end, item.source)))


def _lexemes(layer: SemanticLayer) -> list[MetricLexeme]:
    lexemes: list[MetricLexeme] = []
    for metric in layer.metrics:
        lexemes.extend(_metric_lexemes(metric, layer.terms))
    for term in layer.terms:
        for metric_id in _term_metrics(term, layer):
            lexemes.append(
                MetricLexeme(
                    text=term.term,
                    source=f"term:{term.term}.term",
                    metric_id=metric_id,
                    match_kind="exact",
                    term_id=f"term/{term.term}",
                )
            )
            lexemes.extend(
                MetricLexeme(
                    text=name,
                    source=f"term:{term.term}.synonyms[{index}]",
                    metric_id=metric_id,
                    match_kind="synonym",
                    term_id=f"term/{term.term}",
                )
                for index, name in enumerate(term.synonyms)
            )
    return lexemes


def _metric_lexemes(metric: MetricDefinition, terms: list[TermDefinition]) -> list[MetricLexeme]:
    names = [("name", metric.name)]
    if metric.english_name:
        names.append(("english_name", metric.english_name))
    return [
        *(
            MetricLexeme(
                text=name,
                source=f"metric:{metric.id}.{field}",
                metric_id=metric.id,
                match_kind="exact",
                term_id=_term_for(terms, metric.id, name),
            )
            for field, name in names
        ),
        *(
            MetricLexeme(
                text=name,
                source=f"metric:{metric.id}.synonyms[{index}]",
                metric_id=metric.id,
                match_kind="synonym",
                term_id=_term_for(terms, metric.id, name),
            )
            for index, name in enumerate(metric.synonyms)
        ),
    ]


def _identifier_pattern(identifier: str) -> str:
    words = re.split(r"[_\-\s]+", identifier.casefold())
    if not all(words):
        return r"(?!)"
    tokens = ["(?:" + "|".join(map(re.escape, _word_forms(word))) + ")" for word in words]
    return r"(?<![A-Za-z0-9_])" + r"[_\-\s]+".join(tokens) + r"(?![A-Za-z0-9_])"


def _word_forms(word: str) -> tuple[str, ...]:
    if not word.isascii() or not word.isalpha():
        return (word,)
    base = word
    if word.endswith("es") and word[:-2].endswith(("s", "x", "z", "ch", "sh", "o")):
        base = word[:-2]
    elif len(word) > 1 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        base = word[:-1]
    plural = base + ("es" if base.endswith(("s", "x", "z", "ch", "sh", "o")) else "s")
    return tuple(sorted({word, base, plural}, key=lambda value: (-len(value), value)))


def _term_metrics(term: TermDefinition, layer: SemanticLayer) -> list[str]:
    if term.means.kind == "metric":
        return [item.id for item in layer.metrics if item.id == term.means.id]
    if term.means.kind == "column":
        return [item.id for item in layer.metrics if item.measure.column == term.means.id]
    return []


def _term_for(terms: list[TermDefinition], metric_id: str, phrase: str) -> str | None:
    return next(
        (
            f"term/{item.term}"
            for item in terms
            if item.means.kind == "metric"
            and item.means.id == metric_id
            and phrase in [item.term, *item.synonyms]
        ),
        None,
    )


def _evidence(hit: re.Match[str], lexeme: MetricLexeme) -> MatchEvidence:
    return MatchEvidence(
        start=hit.start(),
        end=hit.end(),
        text=hit.group(),
        source=lexeme.source,
        match_kind=lexeme.match_kind,
        metric_id=lexeme.metric_id,
        term_id=lexeme.term_id,
    )
