# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve the registered subject's input or result role before asset-level defaults."""

import re
from typing import Literal

from datakeel.ask import knowledge_vocabulary as vocabulary
from datakeel.ask.knowledge_focus import QuestionDirection, QuestionFocus
from datakeel.ask.knowledge_frames import counterfactual_direction, question_frame_direction
from datakeel.ask.knowledge_names import SubjectMention
from datakeel.ask.knowledge_scope import clause_scope, question_scope


def _role_direction(text: str, mention: SubjectMention, focus: QuestionFocus) -> QuestionDirection:
    marked = text[: mention.start] + vocabulary.SUBJECT_MARKER + text[mention.end :]
    for direction in (
        _production_purpose(marked, mention),
        question_frame_direction(marked, mention),
        _english_arguments(marked, mention, focus),
        _chinese_arguments(marked, mention, focus),
        _recipient_usage(marked, mention, focus),
        _topic_usage(marked, mention, focus),
        _relative_usage(marked, mention, focus),
    ):
        if direction.value:
            return direction
    for pattern in vocabulary.SOURCE_ROLES:
        if hit := re.search(pattern, marked):
            return QuestionDirection(
                value="downstream", words=_role_words(hit, mention), rule_id="K11-subject-role"
            )
    for pattern in vocabulary.RESULT_ROLES:
        if hit := re.search(pattern, marked):
            return QuestionDirection(
                value="upstream", words=_role_words(hit, mention), rule_id="K11-subject-role"
            )
    return QuestionDirection()


def _role_words(hit: re.Match[str], mention: SubjectMention) -> tuple[str, ...]:
    return (hit.group().replace(vocabulary.SUBJECT_MARKER, mention.text),)


def question_direction(
    text: str, mention: SubjectMention, focus: QuestionFocus
) -> QuestionDirection:
    """Use explicit sentence roles, passive voice, then directional relation language."""
    marked = (
        text[: mention.start]
        + vocabulary.SUBJECT_MARKER
        + " " * (mention.end - mention.start - 1)
        + text[mention.end :]
    )
    counterfactual = counterfactual_direction(marked, mention)
    text = question_scope(marked)
    if vocabulary.SUBJECT_MARKER not in text:
        return counterfactual
    position = text.index(vocabulary.SUBJECT_MARKER)
    mention = mention.model_copy(update={"start": position, "end": position + 1})
    text = text.replace(vocabulary.SUBJECT_MARKER, " ")
    role = counterfactual if counterfactual.value else _role_direction(text, mention, focus)
    if role.value:
        return role
    hierarchy_text = re.sub(vocabulary.NEUTRAL_RELATION, lambda hit: " " * len(hit.group()), text)
    for value, pattern in (
        ("downstream", vocabulary.HIERARCHY_DOWN),
        ("upstream", vocabulary.HIERARCHY_UP),
    ):
        if hit := re.search(pattern, hierarchy_text):
            return _modifier_relation(text, mention, focus, hit) or QuestionDirection(
                value="upstream" if value == "upstream" else "downstream", words=(hit.group(),)
            )
    passive = _passive_direction(text, mention)
    if passive.value:
        return passive
    conditional = _conditional_direction(text, mention)
    if conditional.value:
        return conditional
    return _verb_direction(text, mention, focus)


def _modifier_relation(
    text: str, mention: SubjectMention, focus: QuestionFocus, hierarchy: re.Match[str]
) -> QuestionDirection | None:
    if hierarchy.end() > focus.start or not re.fullmatch(
        vocabulary.HIERARCHY_NOUN_GAP, text[hierarchy.end() : focus.start]
    ):
        return None
    scoped = clause_scope(text, mention.start, focus.start)
    for candidate in (
        _passive_direction(scoped, mention),
        _conditional_direction(scoped, mention),
    ):
        if candidate.value:
            return candidate
    candidate = _verb_direction(scoped, mention, focus)
    if not candidate.value or not candidate.reliable or not candidate.words:
        return None
    word = candidate.words[0]
    if word in vocabulary.SOURCE_PREPOSITIONS:
        return None
    start = scoped.find(word)
    end = start + len(word)
    gap = scoped[mention.end : start] if mention.start < start else scoped[end : mention.start]
    return candidate if re.fullmatch(vocabulary.PREDICATE_LINK, gap) else None


def _passive_direction(text: str, mention: SubjectMention) -> QuestionDirection:
    if hit := re.search(
        rf"(?:被|由).*?(?:{vocabulary.USAGE_ZH})|"
        rf"\b(?:{vocabulary.USAGE_EN_PAST})\s+by\b",
        text,
    ):
        actor = (
            hit.start() < mention.start < hit.end()
            if hit.group().startswith(("被", "由"))
            else mention.start >= hit.end()
        )
        return QuestionDirection(
            value="upstream" if actor else "downstream",
            words=tuple(part for part in re.split(r"\s{2,}", hit.group()) if part),
        )
    if hit := re.search(rf"(?:被|由).*?(?:{vocabulary.PRODUCTION_ZH})", text):
        inside = hit.start() < mention.start < hit.end()
        return QuestionDirection(value="downstream" if inside else "upstream", words=(hit.group(),))
    if hit := re.search(rf"\b(?:{vocabulary.PRODUCTION_EN_PAST})\s+by\b", text):
        actor = mention.start >= hit.end()
        return QuestionDirection(value="downstream" if actor else "upstream", words=(hit.group(),))
    return QuestionDirection()


def _conditional_direction(text: str, mention: SubjectMention) -> QuestionDirection:
    if hit := re.search(vocabulary.ABSENCE_PREPOSITION, text):
        source = mention.start >= hit.end() and not re.search(
            vocabulary.QUESTION_ANCHOR, text[hit.end() : mention.start]
        )
        return QuestionDirection(value="downstream" if source else "upstream", words=(hit.group(),))
    event = _event_source(text, mention)
    if event.value:
        return event
    condition = re.search(vocabulary.CONDITION_WORDS, text)
    if not condition:
        return QuestionDirection()
    absence = re.search(vocabulary.ABSENCE_WORDS, text[condition.end() :])
    if not absence:
        return QuestionDirection()
    end = condition.end() + absence.end()
    if re.search(vocabulary.CLAUSE_DELIMITER, text[condition.end() : end]):
        return QuestionDirection()
    source = (
        condition.end() <= mention.start
        and not re.search(vocabulary.QUESTION_ANCHOR, text[condition.end() : mention.start])
        and not re.search(vocabulary.CLAUSE_DELIMITER, text[condition.end() : mention.start])
    ) or (
        mention.end <= condition.start()
        and re.fullmatch(vocabulary.TOPIC_CONDITION_GAP, text[mention.end : condition.start()])
        and re.fullmatch(
            vocabulary.PREDICATE_LINK,
            text[condition.end() : condition.end() + absence.start()],
        )
    )
    return QuestionDirection(
        value="downstream" if source else "upstream",
        words=(text[condition.start() : end],),
    )


def _event_source(text: str, mention: SubjectMention) -> QuestionDirection:
    marked = text[: mention.start] + vocabulary.SUBJECT_MARKER + text[mention.end :]
    event = re.search(vocabulary.SOURCE_EVENT_PREFIX, marked)
    if event:
        after = marked[event.end() :]
        if re.search(vocabulary.QUESTION_ANCHOR, after) and re.search(vocabulary.IMPACT, after):
            return _frame_result("downstream", event, mention)
    return QuestionDirection()


def _impact_direction(text: str, mention: SubjectMention) -> QuestionDirection:
    marked = text[: mention.start] + vocabulary.SUBJECT_MARKER + text[mention.end :]
    for pattern in (
        vocabulary.CAUSAL_INPUT,
        vocabulary.IMPACT_SOURCE_ROLE,
        vocabulary.IMPACT_CONDITION_SOURCE,
    ):
        if hit := re.search(pattern, marked):
            return QuestionDirection(value="downstream", words=_role_words(hit, mention))
    if hit := re.search(vocabulary.IMPACT_PASSIVE, text):
        actor = mention.start >= hit.end()
        return QuestionDirection(value="downstream" if actor else "upstream", words=(hit.group(),))
    if hit := re.search(vocabulary.IMPACT, text):
        before = mention.end <= hit.start()
        return QuestionDirection(value="downstream" if before else "upstream", words=(hit.group(),))
    return QuestionDirection()


def _verb_direction(text: str, mention: SubjectMention, focus: QuestionFocus) -> QuestionDirection:
    impact = _impact_direction(text, mention)
    if impact.value:
        return impact
    if hit := re.search(vocabulary.FLOW_DESTINATION, text):
        before = mention.end <= hit.start()
        return QuestionDirection(value="downstream" if before else "upstream", words=(hit.group(),))
    for hit in re.finditer(vocabulary.FLOW_DEPENDENCY, text):
        if _framing_preposition(text, hit, mention, focus):
            continue
        after = mention.start >= hit.end() and not (hit.end() <= focus.start < mention.start)
        return QuestionDirection(value="downstream" if after else "upstream", words=(hit.group(),))
    if hit := re.search(vocabulary.SOURCE_NOUNS, text):
        return QuestionDirection(value="upstream", words=(hit.group(),), reliable=False)
    if re.search(vocabulary.CALCULATION_QUESTION, text):
        return QuestionDirection(value="upstream", words=(focus.text,))
    return QuestionDirection()


def _framing_preposition(
    text: str, hit: re.Match[str], mention: SubjectMention, focus: QuestionFocus
) -> bool:
    if hit.group() not in vocabulary.SOURCE_PREPOSITIONS or mention.start < hit.end():
        return False
    between = text[hit.end() : mention.start].strip()
    if not between:
        return False
    return not (
        hit.end() <= focus.start < mention.start and re.match(vocabulary.QUESTION_ANCHOR, between)
    )


def _same_clause_before(text: str, subject: int, start: int) -> bool:
    return subject < start and re.fullmatch(vocabulary.ROLE_CLAUSE, text[subject:start]) is not None


def _frame_result(
    value: Literal["upstream", "downstream"], hit: re.Match[str], mention: SubjectMention
) -> QuestionDirection:
    return QuestionDirection(
        value=value, words=_role_words(hit, mention), rule_id="K11-subject-role"
    )


def _english_arguments(
    marked: str, mention: SubjectMention, focus: QuestionFocus
) -> QuestionDirection:
    subject = mention.start
    for frame in re.finditer(vocabulary.EN_INPUT_FRAME, marked):
        if frame.start("input") <= subject < frame.end("input"):
            return _frame_result("downstream", frame, mention)
        if frame.start("receiver") <= subject < frame.end("receiver"):
            return _frame_result("upstream", frame, mention)
        if not _same_clause_before(marked, subject, frame.start()):
            continue
        before = marked[subject + 1 : frame.start()]
        if frame.group("verb") in vocabulary.PAST_PRODUCTION and re.search(
            vocabulary.PASSIVE_AUXILIARY, before
        ):
            return _frame_result("upstream", frame, mention)
        asked_input = focus.start >= frame.start("input") or not frame.group("input").strip()
        return _frame_result("upstream" if asked_input else "downstream", frame, mention)
    return _supply_arguments(marked, mention)


def _supply_arguments(marked: str, mention: SubjectMention) -> QuestionDirection:
    subject = mention.start
    for frame in re.finditer(vocabulary.EN_SUPPLY_TO, marked):
        if frame.start("receiver") <= subject < frame.end("receiver"):
            return _frame_result("upstream", frame, mention)
        if _same_clause_before(marked, subject, frame.start()):
            return _frame_result("downstream", frame, mention)
    return QuestionDirection()


def _chinese_arguments(
    marked: str, mention: SubjectMention, focus: QuestionFocus
) -> QuestionDirection:
    subject = mention.start
    for frame in re.finditer(vocabulary.ZH_INPUT_FRAME, marked):
        if frame.start("input") <= subject < frame.end("input"):
            return _frame_result("downstream", frame, mention)
        if frame.start("result") <= subject < frame.end("result"):
            return _frame_result("upstream", frame, mention)
        if _same_clause_before(marked, subject, frame.start()):
            asked_input = frame.start("input") <= focus.start < frame.end("input")
            return _frame_result("upstream" if asked_input else "downstream", frame, mention)
    for frame in re.finditer(vocabulary.ZH_PASSIVE_SUPPLY, marked):
        if frame.start("supplier") <= subject < frame.end("supplier"):
            return _frame_result("downstream", frame, mention)
        if _same_clause_before(marked, subject, frame.start()) or subject >= frame.end():
            return _frame_result("upstream", frame, mention)
    return QuestionDirection()


def _relative_usage(
    marked: str, mention: SubjectMention, focus: QuestionFocus
) -> QuestionDirection:
    anchor = re.search(vocabulary.SUBJECT_EXISTENCE, marked)
    if not anchor or not (usage := re.search(vocabulary.USAGE_ZH, marked[anchor.end() :])):
        return QuestionDirection()
    start, end = anchor.end() + usage.start(), anchor.end() + usage.end()
    if re.search(vocabulary.ZH_SUBJECT_PRONOUN, marked[anchor.end() : start]):
        return _frame_result("upstream", anchor, mention)
    if re.search(vocabulary.ZH_SUBJECT_PRONOUN, marked[end:]) or focus.start < start:
        return _frame_result("downstream", anchor, mention)
    return QuestionDirection()


def _recipient_usage(
    marked: str, mention: SubjectMention, focus: QuestionFocus
) -> QuestionDirection:
    subject = mention.start
    for frame in re.finditer(vocabulary.ZH_RECIPIENT_USAGE, marked):
        if frame.start("consumer") <= subject < frame.end("consumer"):
            return _frame_result("upstream", frame, mention)
        if frame.start("resource") <= subject < frame.end("resource"):
            return _frame_result("downstream", frame, mention)
        if _same_clause_before(marked, subject, frame.start()):
            asked_consumer = frame.start("consumer") <= focus.start < frame.end("consumer")
            return _frame_result("downstream" if asked_consumer else "upstream", frame, mention)
    return QuestionDirection()


def _topic_usage(marked: str, mention: SubjectMention, focus: QuestionFocus) -> QuestionDirection:
    for frame in re.finditer(vocabulary.ZH_TOPIC_USAGE, marked):
        if not frame.start("actor") <= focus.start < frame.end("actor"):
            continue
        auxiliary = marked[focus.start + len(focus.text) : frame.start("usage")]
        if re.fullmatch(vocabulary.PREDICATE_LINK, auxiliary) and re.fullmatch(
            vocabulary.ZH_ELIDED_OBJECT, frame.group("object")
        ):
            return _frame_result("downstream", frame, mention)
    return QuestionDirection()


def _production_purpose(marked: str, mention: SubjectMention) -> QuestionDirection:
    for frame in re.finditer(vocabulary.PRODUCTION_PURPOSE_EN, marked):
        if frame.start("result") <= mention.start < frame.end("result"):
            prefix = marked[frame.start("result") : mention.start].strip()
            if not prefix or re.fullmatch(vocabulary.NOUN_FILLER, prefix + " "):
                return _frame_result("upstream", frame, mention)
        before = marked[mention.start + 1 : frame.start()]
        passive = re.search(vocabulary.PASSIVE_AUXILIARY, before) or re.search(
            vocabulary.PASSIVE_AUXILIARY, marked[: mention.start]
        )
        if (
            mention.start < frame.start()
            and passive
            and re.fullmatch(vocabulary.PREDICATE_LINK, before)
        ):
            return _frame_result("downstream", frame, mention)
    return QuestionDirection()
