# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound the main question while preserving resolved subject and token coordinates."""

import re

from datakeel.ask import knowledge_vocabulary as vocabulary

_RELATIVE_PREDICATES = 2
_NAMING_QUESTION = (
    r"\b(?:what|how)\s+(?:is|are|was|were)\s+(?:it|they|these|those)\s+called\b[?!.\s]*$"
)


def _naming_tail(text: str) -> str:
    naming = re.search(_NAMING_QUESTION, text)
    if naming and re.search(
        rf"(?:{vocabulary.FLOW_DEPENDENCY})|(?:{vocabulary.NEUTRAL_RELATION})",
        text[: naming.start()],
    ):
        return text[: naming.start()] + " " * (len(text) - naming.start())
    return text


def _supplementary(hit: re.Match[str]) -> str:
    clause = hit.group()
    body = re.sub(r"^,\s*(?:which|that)\s+", "", clause)
    noun = "|".join(pattern for _, pattern in vocabulary.TYPE_WORDS)
    if re.match(rf"{vocabulary.NOUN_FILLER}(?:{noun})|{vocabulary.QUESTION_PLACEHOLDER}", body):
        return clause
    return " " * len(clause)


def _topic_subject(text: str) -> str:
    topic = re.search(vocabulary.TOPIC_WITH_SUBJECT, text)
    if not topic:
        return text
    tail = text[topic.end() :]
    question = re.search(rf"(?:{vocabulary.QUESTION_ANCHOR})|(?:{vocabulary.LIST_QUESTION})", tail)
    if not question:
        return text
    start = topic.end() + question.start()
    clause = clause_scope(text, start, start)
    pronoun = re.search(vocabulary.SUBJECT_PRONOUN, clause[topic.end() :])
    if not pronoun:
        return text
    start = topic.end() + pronoun.start()
    text = clause_scope(text, start, start).replace(vocabulary.SUBJECT_MARKER, " ")
    return (
        text[:start]
        + vocabulary.SUBJECT_MARKER
        + " " * (len(pronoun.group()) - 1)
        + text[start + len(pronoun.group()) :]
    )


def question_scope(text: str) -> str:
    """Mask supplementary clauses, keeping a main-clause pronoun bound to its subject."""
    original = text
    text = _naming_tail(text)
    for pattern in vocabulary.SUPPLEMENTARY_CLAUSES:
        text = re.sub(pattern, _supplementary, text)
    if (apposition := re.search(vocabulary.NOMINAL_APPOSITION, text)) and re.search(
        vocabulary.QUESTION_ANCHOR, text[: apposition.start()]
    ):
        text = text[: apposition.start()] + " " * len(apposition.group()) + text[apposition.end() :]
    if hit := re.search(vocabulary.CONCESSIVE_CLAUSE, text):
        text = " " * hit.end() + text[hit.end() :]
    if (hit := re.search(vocabulary.TEMPORAL_CLAUSE, text)) and re.search(
        vocabulary.QUESTION_ANCHOR, text[: hit.start()]
    ):
        text = text[: hit.start()] + " " * (len(text) - hit.start())
    if (
        vocabulary.SUBJECT_MARKER in original
        and vocabulary.SUBJECT_MARKER not in text
        and (pronoun := re.search(vocabulary.SUBJECT_PRONOUN, text))
    ):
        text = (
            text[: pronoun.start()]
            + vocabulary.SUBJECT_MARKER
            + " " * (len(pronoun.group()) - 1)
            + text[pronoun.end() :]
        )
    return _topic_subject(text)


def clause_scope(text: str, first: int, second: int) -> str:
    """Keep the smallest punctuation-bounded span containing both argument positions."""
    low, high = sorted((first, second))
    boundaries = tuple(re.finditer(vocabulary.CLAUSE_DELIMITER, text))
    start = max((hit.end() for hit in boundaries if hit.end() <= low), default=0)
    end = min((hit.start() for hit in boundaries if hit.start() > high), default=len(text))
    return " " * start + text[start:end] + " " * (len(text) - end)


def relation_scope(text: str, subject: int, focus_start: int, focus_end: int) -> str:
    """Keep the predicate attaching the resolved asset to the requested noun phrase."""
    if focus_start < 0:
        return text
    marked = text[:subject] + vocabulary.SUBJECT_MARKER + text[subject + 1 :]
    bound = question_scope(marked)
    if vocabulary.SUBJECT_MARKER in bound:
        subject = bound.index(vocabulary.SUBJECT_MARKER)
    if scoped := _english_relative_scope(text, subject, focus_end):
        return scoped
    return _chinese_relative_scope(text, subject, focus_start, focus_end) or text


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + " " * (end - start) + text[end:]


def _english_relative_scope(text: str, subject: int, focus_end: int) -> str | None:
    anchor = re.match(vocabulary.RELATIVE_ANCHOR_EN, text[focus_end:])
    if not anchor:
        return None
    start = focus_end + anchor.start()
    body = focus_end + anchor.end()
    boundary = re.search(vocabulary.CLAUSE_DELIMITER, text[body:])
    end = body + boundary.start() if boundary else len(text)
    if subject < start:
        ambiguous = re.search(vocabulary.CLAUSE_DELIMITER, text[subject:start]) or re.search(
            vocabulary.SUBJECT_PRONOUN, text[start:end]
        )
        return None if ambiguous else _blank(text, start, end)
    predicates = tuple(re.finditer(vocabulary.RELATION_PREDICATE, text[body:end]))
    if len(predicates) != _RELATIVE_PREDICATES:
        return None
    first, second = predicates
    first_end = body + first.end()
    second_start = body + second.start()
    auxiliary = re.search(vocabulary.RELATIVE_MAIN_AUXILIARY, text[first_end:subject])
    main_start = first_end + auxiliary.start() if auxiliary else second_start
    if subject >= second_start or (first_end <= subject and auxiliary):
        return _blank(text, start, main_start)
    return _blank(text, second_start, end)


def _chinese_relative_scope(
    text: str, subject: int, focus_start: int, focus_end: int
) -> str | None:
    tail = re.search(vocabulary.RELATIVE_HEAD_END_ZH, text[:focus_start])
    if not tail:
        return None
    anchors = tuple(re.finditer(vocabulary.RELATIVE_QUESTION_ANCHOR, text[: tail.start()]))
    if not anchors:
        return None
    start = anchors[-1].end()
    if re.search(vocabulary.CLAUSE_DELIMITER, text[start:focus_start]) or (
        subject < start and re.search(vocabulary.SUBJECT_PRONOUN, text[start:focus_start])
    ):
        return None
    predicates = tuple(re.finditer(vocabulary.RELATION_PREDICATE, text[start : tail.start()]))
    if len(predicates) != 1:
        return None
    if start <= subject < tail.start():
        boundary = re.search(vocabulary.CLAUSE_DELIMITER, text[focus_end:])
        end = focus_end + boundary.start() if boundary else len(text)
        return _blank(text, focus_end, end)
    return _blank(text, start, tail.end())
