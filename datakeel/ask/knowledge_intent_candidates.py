# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional model intent candidate proposal verified by deterministic subject and slot guards."""

import re
from typing import Literal

from pydantic import ValidationError

from datakeel.ask import knowledge_vocabulary as vocabulary
from datakeel.ask.knowledge_names import normalize_name
from datakeel.ask.knowledge_parser import KnowledgeQuestion
from datakeel.ask.knowledge_scope import question_scope
from datakeel.core.agent_models import ChatMessage, ModelRequest, Provider
from datakeel.core.errors import DatakeelError
from datakeel.core.knowledge_models import KnowledgeFocus, KnowledgeIntent, KnowledgeSubject
from datakeel.core.models import BoundaryModel

CandidateIntent = Literal["owner", "upstream", "downstream", "owned", "none"]
_ELIGIBLE_RULES = frozenset(
    {"K3-person-focus", "K5-metric-source", "K7-location-source", "K8-ambiguous-intent"}
)
_SYSTEM_PROMPT = (
    'Return only JSON {"intent": "owner"|"upstream"|"downstream"|"owned"|"none"}. '
    "Classify only the relationship direction or ownership for the supplied subject. "
    "Never produce SQL, numbers, or new subject names."
)


class KnowledgeIntentCandidateRequest(BoundaryModel):
    """Bound the prompt payload to the already resolved subject, focus, and valid choices."""

    question: str
    subject: str
    subject_kind: str
    focus: KnowledgeFocus
    allowed_intents: tuple[KnowledgeIntent, ...]


class CandidateIntentProposal(BoundaryModel):
    """Restrict untrusted model output to one closed intent token."""

    intent: CandidateIntent


def refine_knowledge_intent(
    question: str,
    parsed: KnowledgeQuestion,
    provider: Provider,
    *,
    model: str = "fake-knowledge-intent",
) -> KnowledgeQuestion:
    """Propose an intent candidate for unresolved or fallback rules, then verify by rule."""
    if not _eligible_for_candidate(question, parsed):
        return parsed
    subject = parsed.candidates[0]
    allowed = _allowed_intents(parsed, subject)
    payload = KnowledgeIntentCandidateRequest(
        question=question,
        subject=subject.name,
        subject_kind=subject.entity_type or subject.kind,
        focus=parsed.recognition.focus,
        allowed_intents=allowed,
    )
    try:
        response = provider.complete(
            ModelRequest(
                model=model,
                tools=[],
                segments=[],
                messages=[
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=payload.model_dump_json()),
                ],
            )
        )
        proposal = CandidateIntentProposal.model_validate_json(response.content)
    except (DatakeelError, ValidationError, ValueError):
        return parsed
    verified = verify_candidate_intent(parsed, proposal.intent)
    if verified is None or (verified == parsed.intent and not parsed.intent_candidates):
        return parsed
    return _apply_verified_intent(parsed, verified)


def _apply_verified_intent(
    parsed: KnowledgeQuestion, verified: KnowledgeIntent
) -> KnowledgeQuestion:
    direction: Literal["upstream", "downstream"] | None = (
        "upstream" if verified == "upstream" else "downstream" if verified == "downstream" else None
    )
    words = (
        parsed.recognition.direction_text
        if direction and parsed.recognition.direction_text
        else (parsed.recognition.focus_text,)
        if direction and parsed.recognition.focus_text
        else ()
    )
    return parsed.model_copy(
        update={
            "intent": verified,
            "intent_candidates": (),
            "unsupported_phrasing": False,
            "recognition": parsed.recognition.model_copy(
                update={
                    "direction": direction,
                    "direction_text": words,
                    "rule_id": "K18-verified-model-candidate",
                }
            ),
        }
    )


def verify_candidate_intent(
    parsed: KnowledgeQuestion, candidate: CandidateIntent
) -> KnowledgeIntent | None:
    """Accept a model candidate only when subject, focus, options, and direction agree."""
    if candidate == "none" or len(parsed.candidates) != 1:
        return None
    allowed = _allowed_intents(parsed, parsed.candidates[0])
    if candidate not in allowed:
        return None
    prior = (
        parsed.recognition.direction
        if parsed.recognition.rule_id not in {"K5-metric-source", "K7-location-source"}
        else None
    )
    if prior is not None and candidate in {"upstream", "downstream"} and candidate != prior:
        return None
    return candidate


def _eligible_for_candidate(question: str, parsed: KnowledgeQuestion) -> bool:
    if len(parsed.candidates) != 1 or parsed.recognition.rule_id not in _ELIGIBLE_RULES:
        return False
    if parsed.recognition.rule_id != "K3-person-focus":
        return True
    masked = normalize_name(question)
    for item in parsed.recognition.subjects:
        masked = re.sub(re.escape(normalize_name(item.text)), " ", masked)
    return re.search(vocabulary.OWNERSHIP, question_scope(masked)) is None


def _allowed_intents(
    parsed: KnowledgeQuestion, subject: KnowledgeSubject
) -> tuple[KnowledgeIntent, ...]:
    is_person = subject.kind == "owner" or subject.entity_type in {"person", "organization"}
    base: tuple[KnowledgeIntent, ...] = (
        ("owned", "owner") if is_person else ("owner", "upstream", "downstream")
    )
    if parsed.intent_candidates:
        base = tuple(item for item in base if item in parsed.intent_candidates)
    blocked_focus = {"table", "metric"} if is_person else {"table", "metric", "location"}
    if parsed.recognition.focus in blocked_focus:
        base = tuple(item for item in base if item != "owner")
    return base
