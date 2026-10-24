# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve registered subjects, then interrogative focus, direction and answer route."""

import re

from datakeel.ask import knowledge_vocabulary as vocabulary
from datakeel.ask.knowledge_focus import (
    QuestionDirection,
    QuestionFocus,
    has_relation,
    masked_subjects,
    question_focus,
)
from datakeel.ask.knowledge_names import SubjectMention, normalize_name
from datakeel.ask.knowledge_roles import question_direction
from datakeel.ask.knowledge_routing import grouped_request, numeric_route, pure_metric_phrase
from datakeel.ask.knowledge_scope import question_scope, relation_scope
from datakeel.ask.knowledge_subjects import subject_mentions
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.knowledge_models import (
    KnowledgeIntent,
    KnowledgeRecognition,
    KnowledgeSubject,
    KnowledgeSubjectMatch,
)
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import BoundaryModel


class KnowledgeQuestion(BoundaryModel):
    """Retain subject-first resolution and a replayable deterministic decision trace."""

    intent: KnowledgeIntent
    subject: str
    candidates: tuple[KnowledgeSubject, ...] = ()
    intent_candidates: tuple[KnowledgeIntent, ...] = ()
    recognition: KnowledgeRecognition
    unsupported_phrasing: bool = False
    count_focus: QuestionFocus | None = None


def parse_knowledge_question(
    question: str,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
    context: LinkContext | None = None,
    *,
    subject_id: str | None = None,
) -> KnowledgeQuestion | None:
    """Find subjects before interpreting focus; keep metric routing graph-independent."""
    text = normalize_name(question)
    mentions = subject_mentions(question, catalog, layer, context or LinkContext())
    numeric_text = masked_subjects(text, mentions)
    numeric_focus = question_focus(numeric_text)
    if numeric_route(numeric_text, numeric_focus, question=text) or pure_metric_phrase(
        question, layer
    ):
        return None
    if subject_id:
        mentions = tuple(
            item.model_copy(
                update={
                    "candidates": tuple(
                        candidate
                        for candidate in item.candidates
                        if candidate.asset_ref.asset_id == subject_id
                    )
                }
            )
            for item in mentions
            if any(candidate.asset_ref.asset_id == subject_id for candidate in item.candidates)
        )
    masked = masked_subjects(text, mentions)
    focus = question_focus(masked)
    if grouped_request(masked, focus):
        return None
    if (focus.kind == "unknown" or (focus.kind == "list" and not mentions)) and not has_relation(
        masked
    ):
        return None
    return _interpret(masked, mentions, focus)


def metric_recognition(
    question: str, catalog: CatalogSnapshot, layer: SemanticLayer
) -> KnowledgeRecognition:
    """Explain numeric, grouped and fallback decisions using catalog vocabulary alone."""
    mentions = subject_mentions(question, catalog, layer, LinkContext())
    text = masked_subjects(normalize_name(question), mentions)
    focus = question_focus(text)
    rule = (
        "M1-numeric"
        if numeric_route(text, focus, question=normalize_name(question))
        else "M2-metric-phrase"
        if pure_metric_phrase(question, layer)
        else "M3-metric-fallback"
    )
    return KnowledgeRecognition(
        subjects=tuple(
            KnowledgeSubjectMatch(text=mention.text, subject=item)
            for mention in mentions
            for item in mention.candidates
        ),
        focus=focus.kind,
        focus_text=focus.text,
        rule_id=rule,
    )


def _interpret(
    text: str, mentions: tuple[SubjectMention, ...], focus: QuestionFocus
) -> KnowledgeQuestion:
    candidates = tuple(
        {item.asset_ref: item for mention in mentions for item in mention.candidates}.values()
    )
    if len(candidates) == 1 and mentions:
        text = relation_scope(text, mentions[0].start, focus.start, focus.start + len(focus.text))
    direction = question_direction(text, mentions[0], focus) if mentions else QuestionDirection()
    intent, options, rule = _intent(candidates, focus, direction, text)
    if intent in {"upstream", "downstream"} and (not direction.value or not direction.reliable):
        direction = QuestionDirection(
            value="upstream" if intent == "upstream" else "downstream",
            words=(focus.text,),
            rule_id=rule,
        )
    return KnowledgeQuestion(
        intent=intent,
        subject=mentions[0].text if mentions else "",
        candidates=candidates,
        intent_candidates=options,
        unsupported_phrasing=bool(options),
        count_focus=focus if focus.counted else None,
        recognition=KnowledgeRecognition(
            subjects=tuple(
                KnowledgeSubjectMatch(text=mention.text, subject=item)
                for mention in mentions
                for item in mention.candidates
            ),
            focus=focus.kind,
            focus_text=focus.text,
            direction=direction.value,
            direction_text=direction.words,
            rule_id=rule,
        ),
    )


def _intent(
    subjects: tuple[KnowledgeSubject, ...],
    focus: QuestionFocus,
    direction: QuestionDirection,
    text: str,
) -> tuple[KnowledgeIntent, tuple[KnowledgeIntent, ...], str]:
    if not subjects:
        return "related", (), "K0-unknown-subject"
    if len(subjects) > 1:
        return "related", (), "K1-ambiguous-subject"
    subject = next(iter(subjects))
    if subject.kind == "owner" or subject.entity_type in {"person", "organization"}:
        if not _employment(text, focus):
            return "owned", (), "K2-person-owned"
        return "related", ("owned", "owner"), "K8-ambiguous-intent"
    return _asset_intent(subject, focus, direction, text)


def _employment(text: str, focus: QuestionFocus) -> bool:
    if focus.kind in {"table", "metric"}:
        return False
    if focus.kind in {"person", "location"} and re.search(vocabulary.WORK_WORDS, text):
        return True
    return re.search(vocabulary.EMPLOYMENT, text) is not None


def _asset_intent(
    subject: KnowledgeSubject,
    focus: QuestionFocus,
    direction: QuestionDirection,
    text: str,
) -> tuple[KnowledgeIntent, tuple[KnowledgeIntent, ...], str]:
    if focus.kind == "person" and _owner_focus(text, focus, direction):
        return "owner", (), "K3-person-focus"
    if direction.value and direction.reliable:
        return direction.value, (), direction.rule_id
    if default := _default_asset_intent(subject, focus):
        return default
    if direction.value:
        return direction.value, (), direction.rule_id
    options: tuple[KnowledgeIntent, ...] = ("upstream", "downstream")
    if focus.kind not in {"table", "metric"}:
        options = (*options, "owner")
    return "related", options, "K8-ambiguous-intent"


def _owner_focus(text: str, focus: QuestionFocus, direction: QuestionDirection) -> bool:
    text = question_scope(text)
    ownership = re.search(vocabulary.OWNERSHIP, text)
    dependency = re.search(vocabulary.PERSON_DEPENDENCY, text)
    if ownership and (
        not dependency
        or ownership.start() < dependency.start()
        or dependency.start() < focus.start < ownership.start()
    ):
        return True
    if direction.value == "downstream":
        return False
    explicit_role = direction.rule_id == "K11-subject-role"
    return not (direction.value and direction.reliable and (dependency or explicit_role))


def _default_asset_intent(
    subject: KnowledgeSubject, focus: QuestionFocus
) -> tuple[KnowledgeIntent, tuple[KnowledgeIntent, ...], str] | None:
    metric = subject.kind == "metric" or subject.entity_type == "metric"
    if metric and focus.kind in {"table", "location"}:
        return "upstream", (), "K5-metric-source"
    if not metric and focus.kind == "metric":
        return "downstream", (), "K6-table-metrics"
    if hierarchy := _hierarchy_intent(subject, focus):
        return hierarchy
    if focus.kind == "location":
        return "upstream", (), "K7-location-source"
    return None


def _hierarchy_intent(
    subject: KnowledgeSubject, focus: QuestionFocus
) -> tuple[KnowledgeIntent, tuple[KnowledgeIntent, ...], str] | None:
    subject_level = vocabulary.ASSET_LEVELS.get(subject.kind)
    target_level = vocabulary.ASSET_LEVELS.get(focus.target_kind or "")
    if subject_level is None or target_level is None or subject_level == target_level:
        return None
    direction = "upstream" if subject_level > target_level else "downstream"
    rule = "K9-hierarchy-upstream" if direction == "upstream" else "K10-hierarchy-downstream"
    return direction, (), rule
