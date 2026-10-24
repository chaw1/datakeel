# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find requested catalog types after hiding resolved names and their type labels."""

import re
from typing import Literal

from datakeel.ask import knowledge_vocabulary as vocabulary
from datakeel.ask.knowledge_names import SubjectMention
from datakeel.ask.knowledge_scope import question_scope
from datakeel.core.knowledge_models import KnowledgeFocus
from datakeel.core.models import BoundaryModel


class QuestionFocus(BoundaryModel):
    """Retain public focus plus the exact internal catalog type and count request."""

    kind: KnowledgeFocus = "unknown"
    text: str = ""
    start: int = -1
    target_kind: vocabulary.CatalogTarget | None = None
    counted: bool = False


class QuestionDirection(BoundaryModel):
    """Explain the resolved subject's dependency role without adding public schema."""

    value: Literal["upstream", "downstream"] | None = None
    words: tuple[str, ...] = ()
    rule_id: str = "K4-direction"
    reliable: bool = True


def masked_subjects(text: str, mentions: tuple[SubjectMention, ...]) -> str:
    """Hide registered names and adjacent subject labels while preserving coordinates."""
    chars = list(text)
    for item in mentions:
        start = item.start
        end = item.end
        if prefix := re.search(vocabulary.SUBJECT_PREFIX, text[:start]):
            interrogative = rf"(?:{vocabulary.TYPED_QUESTION}|{vocabulary.COUNT_QUESTION})$"
            if not re.search(interrogative, text[: prefix.start()]):
                start = prefix.start()
        if suffix := re.match(vocabulary.SUBJECT_SUFFIX, text[end:]):
            end += suffix.end()
        chars[start:end] = " " * (end - start)
    return "".join(chars)


class _Noun(BoundaryModel):
    kind: vocabulary.CatalogTarget
    start: int
    end: int


def _nouns(text: str) -> tuple[_Noun, ...]:
    found = sorted(
        (
            _Noun(kind=kind, start=hit.start(), end=hit.end())
            for kind, pattern in vocabulary.TYPE_WORDS
            for hit in re.finditer(pattern, text)
        ),
        key=lambda item: (item.start, -item.end),
    )
    result: list[_Noun] = []
    for item in found:
        if not result or item.start >= result[-1].end:
            result.append(item)
    return tuple(result)


def _noun_focus(text: str, noun: _Noun, *, counted: bool = False) -> QuestionFocus:
    return QuestionFocus(
        kind=vocabulary.FOCUS_KINDS[noun.kind],
        target_kind=noun.kind,
        text=text[noun.start : noun.end],
        start=noun.start,
        counted=counted,
    )


def _phrase_head(text: str, nouns: tuple[_Noun, ...], start: int) -> _Noun | None:
    following = tuple(item for item in nouns if item.start >= start)
    if not following:
        return None
    head = following[0]
    prefix = text[start : head.start]
    if re.search(vocabulary.NOUN_CLAUSE_BOUNDARY, prefix):
        return None
    if re.search(r"[a-z]", prefix) and not re.fullmatch(
        vocabulary.NOUN_FILLER, prefix.strip() + " "
    ):
        return None
    # Chinese attributes precede their head; English compound noun heads come last.
    for candidate in following[1:]:
        between = text[head.end : candidate.start]
        if _compound_head(between, head, candidate):
            head = candidate
        else:
            break
    return head


def _compound_head(between: str, current: _Noun, candidate: _Noun) -> bool:
    if re.fullmatch(r"\s*", between):
        return True
    # Normalization leaves one space; longer gaps identify hidden registered subjects.
    if re.search(r"[,\uff0c?\uff1f]|\s{2,}", between):
        return False
    if between.rstrip().endswith("的"):
        return True
    return (
        candidate.kind in {"person", "team"}
        and current.kind not in {"person", "team"}
        and re.fullmatch(vocabulary.OWNERSHIP, between.strip()) is not None
    )


def _typed_focus(text: str, prefix: str, *, counted: bool = False) -> QuestionFocus | None:
    nouns = _nouns(text)
    for anchor in re.finditer(prefix, text):
        if head := _phrase_head(text, nouns, anchor.end()):
            if counted and re.search(vocabulary.BUSINESS_COUNT, text[anchor.end() : head.start]):
                continue
            return _noun_focus(text, head, counted=counted)
    return None


def _nominal_focus(text: str, *, counted: bool = False) -> QuestionFocus | None:
    nouns = _nouns(text)
    if not nouns:
        return None
    head = nouns[0]
    for item in nouns[1:]:
        between = text[head.end : item.start]
        if re.search(r"[,\uff0c;\uff1b]", between):
            break
        if _compound_head(between, head, item):
            head = item
    return _noun_focus(text, head, counted=counted)


def _adjacent_focus(text: str, prefix: str) -> QuestionFocus | None:
    """Retain bounded legacy number/ranking syntax without changing the phrase head."""
    for target_kind, noun in vocabulary.TYPE_WORDS:
        if hit := re.search(rf"(?:{prefix})(?:{noun})", text):
            return QuestionFocus(
                kind=vocabulary.FOCUS_KINDS[target_kind],
                target_kind=target_kind,
                text=hit.group(),
                start=hit.start(),
            )
    return None


def question_focus(text: str) -> QuestionFocus:
    """Prefer counted and direct types, then recover nouns separated from a generic ask."""
    text = question_scope(text)
    text = re.sub(vocabulary.SUBJECT_TYPE_PRONOUN, lambda hit: " " * len(hit.group()), text)
    if counted := _typed_focus(text, vocabulary.COUNT_PREFIX, counted=True) or (
        _nominal_focus(text, counted=True) if re.search(vocabulary.COUNT_TOTAL, text) else None
    ):
        return counted
    if typed := _typed_focus(text, vocabulary.TYPE_QUESTION_ANCHOR) or _adjacent_focus(
        text, vocabulary.TYPED_QUESTION
    ):
        return typed
    if hit := re.search(vocabulary.PERSON_QUESTION, text):
        return QuestionFocus(
            kind="person", text=hit.group(), start=hit.start(), target_kind="person"
        )
    if hit := re.search(vocabulary.LOCATION_QUESTION, text):
        return QuestionFocus(kind="location", text=hit.group(), start=hit.start())
    if hit := re.search(vocabulary.LIST_QUESTION, text):
        return _nominal_focus(text) or QuestionFocus(
            kind="list", text=hit.group(), start=hit.start()
        )
    neutral = _nominal_focus(text) if re.search(vocabulary.NEUTRAL_RELATION, text) else None
    return neutral or QuestionFocus()


def has_relation(text: str) -> bool:
    """Use the shared hierarchy, flow, impact and ownership vocabulary for safe routing."""
    return any(
        re.search(pattern, text)
        for pattern in (
            vocabulary.HIERARCHY_UP,
            vocabulary.HIERARCHY_DOWN,
            vocabulary.FLOW_DESTINATION,
            vocabulary.FLOW_DEPENDENCY,
            vocabulary.SOURCE_NOUNS,
            vocabulary.OWNERSHIP,
            vocabulary.IMPACT,
            vocabulary.COUNTERFACTUAL,
        )
    )
