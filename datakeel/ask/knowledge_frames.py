# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve interrogative source and result slots in bounded dependency frames."""

import re
from typing import Literal

from datakeel.ask import knowledge_vocabulary as vocabulary
from datakeel.ask.knowledge_focus import QuestionDirection
from datakeel.ask.knowledge_names import SubjectMention

_QUESTION = rf"(?:{vocabulary.QUESTION_ANCHOR})|(?:{vocabulary.LOCATION_QUESTION})|\bwhose\b"
_CLAUSE = vocabulary.ROLE_CLAUSE
_REFERENCE = rf"§|(?:{vocabulary.SUBJECT_PRONOUN})"
_USAGE = (
    rf"(?:{vocabulary.USAGE_ZH})|"
    r"\b(?:uses?|consumes?|reads?|depends?\s+on|references?|subscribes?\s+to)\b"
)
_DERIVATION = r"\b(?:derived|built|made|created|generated|produced)\s+(?:from|on|using|with)\b"
_BASIS = r"基础|依据|来源|输入|\b(?:basis|base|foundation|input|source)\b"
_ROLE_FRAMES = (
    (
        rf"(?P<result>{_CLAUSE}?\bwhose)\s+(?:inputs?|sources?|basis|foundation)\s+"
        rf"(?:is|are)\s+(?P<source>{_CLAUSE})"
    ),
    (
        rf"(?P<source>{_CLAUSE}?\bwhose)\s+(?:outputs?|results?|products?)\s+"
        rf"(?:is|are)\s+(?P<result>{_CLAUSE})"
    ),
    rf"(?P<result>{_CLAUSE}?)(?:{_DERIVATION})(?P<source>{_CLAUSE})",
    rf"(?P<result>{_CLAUSE}?)(?:{_USAGE})(?P<source>{_CLAUSE})",
    rf"(?P<result>{_CLAUSE}?)(?:基于|依托)(?P<source>{_CLAUSE})",
    rf"(?P<result>{_CLAUSE}?)(?:在|以)(?P<source>{_CLAUSE}?)(?:的)?(?:{_BASIS})上",
    (
        rf"(?P<result>{_CLAUSE}?)(?:把|拿|以)(?P<source>{_CLAUSE}?)"
        rf"(?:当作|当成|作为|作|为)(?:{_BASIS})"
    ),
    (
        rf"(?P<source>{_CLAUSE}?)(?:被)?(?:当作|当成|作为)(?:{_BASIS})"
        rf"{_CLAUSE}?[,\uff0c]?\s*(?:{vocabulary.PRODUCTION_ZH})(?:了)?(?P<result>{_CLAUSE})"
    ),
)
_ABSENCE = (
    vocabulary.ABSENCE_WORDS
    + r"|断供|停掉|停供|\b(?:retir(?:e|es|ed)|drop(?:s|ped)?|remove[ds]?)\b"
)
_CONSEQUENCE = (
    vocabulary.IMPACT + r"|会坏|无法(?:更新|生成)|不能(?:更新|生成)|"
    r"\b(?:fail\w*|stop\s+(?:working|refreshing)|lose\w*\s+(?:its\s+)?(?:data\s+)?feed)\b"
)
_FLOW = r"流向|流到|流入|去向|下一站|\b(?:flows?|go(?:es)?\s+next)\b"
_INVERSION = r"\b(?:does|do|did|is|are|was|were|has|have|can|could|would|will)\s+§"


def question_frame_direction(marked: str, mention: SubjectMention) -> QuestionDirection:
    """Prefer the interrogative argument slot to the registered name's word order."""
    for pattern in _ROLE_FRAMES:
        for frame in re.finditer(pattern, marked):
            if direction := _asked_slot(frame):
                return _result(direction, frame.group(), mention, "K15-question-slot")
    if direction := _flow_slot(marked):
        return _result(direction, marked, mention, "K17-flow-slot")
    return QuestionDirection()


def _asked_slot(frame: re.Match[str]) -> Literal["upstream", "downstream"] | None:
    source, result = frame.group("source"), frame.group("result")
    source_ask = re.search(_QUESTION, source)
    result_ask = re.search(_QUESTION, result)
    if (
        source_ask
        and not result_ask
        and re.search(_REFERENCE, result)
        and not re.search(vocabulary.IMPACT, source[: source_ask.start()])
    ):
        return "upstream"
    if result_ask and not source_ask and re.search(_REFERENCE, source):
        return "downstream"
    # An inverted question fronts its missing object ahead of the stated actor.
    if result_ask and re.search(_INVERSION, result[result_ask.end() :]):
        return "upstream"
    return None


def _flow_slot(marked: str) -> Literal["upstream", "downstream"] | None:
    for flow in re.finditer(_FLOW, marked):
        before, after = marked[: flow.start()], marked[flow.end() :]
        if not re.search(_REFERENCE, before) or not re.search(vocabulary.LOCATION_QUESTION, marked):
            continue
        if re.match(r"\s+(?:(?:in|out)\s+)?(?:from|out\s+of)\b", after):
            return "upstream"
        return "downstream"
    return None


def counterfactual_direction(marked: str, mention: SubjectMention) -> QuestionDirection:
    """Treat an absent source and its affected result as separate argument slots."""
    if not re.search(_QUESTION, marked):
        return QuestionDirection()
    for condition in re.finditer(vocabulary.CONDITION_WORDS, marked):
        source = marked[condition.end() :]
        boundary = re.search(vocabulary.CLAUSE_DELIMITER, source)
        if boundary:
            source = source[: boundary.start()]
        result = marked[: condition.start()] + marked[condition.end() + len(source) :]
        if not re.search(_ABSENCE, source) or re.search(_QUESTION, source):
            continue
        # A topic may precede an elided conditional source in the same clause.
        topic = marked[: condition.start()]
        known_source = "§" in source or (
            "§" in topic
            and not re.search(_QUESTION, topic)
            and re.fullmatch(r"[\s,:\uff1a\uff0c\u2014\u2013]*", topic[topic.index("§") + 1 :])
        )
        if known_source and re.search(_QUESTION, result) and re.search(_CONSEQUENCE, result):
            return _result("downstream", marked, mention, "K16-counterfactual-slot")
    return QuestionDirection()


def _result(
    direction: Literal["upstream", "downstream"],
    words: str,
    mention: SubjectMention,
    rule: str,
) -> QuestionDirection:
    return QuestionDirection(
        value=direction,
        words=(words.replace(vocabulary.SUBJECT_MARKER, mention.text).strip(),),
        rule_id=rule,
    )
