# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assemble knowledge answers and bounded related claims without model or SQL calls."""

from typing import Literal

from datakeel.ask.knowledge_claims import document_claims
from datakeel.ask.knowledge_parser import KnowledgeQuestion
from datakeel.ask.knowledge_subjects import catalog_subject, subject_candidates, subject_suggestions
from datakeel.ask.knowledge_system import system_records
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.knowledge_models import KnowledgeAnswer, KnowledgeSubject
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import new_id
from datakeel.storage.database import Database
from datakeel.storage.kg_queries import get_source_text
from datakeel.storage.link_queries import read_link_context


def knowledge_answer(
    db: Database,
    request: AskRequest,
    parsed: KnowledgeQuestion,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
) -> AskAnswer:
    """Resolve one subject and retain separate catalog and document sections for every state."""
    context = read_link_context(db)
    candidates = subject_candidates(parsed.subject, catalog, layer, context.entities)
    pinned = request.subject_id or request.metric_id
    if pinned:
        candidates = tuple(item for item in candidates if item.asset_ref.asset_id == pinned)
    if not candidates:
        return _response(
            request,
            KnowledgeAnswer(intent=parsed.intent, reason_code="unknown_subject"),
            "unanswerable",
            "无法定位主语。以下是最接近的指标、表或图谱实体。",
            subject_suggestions(parsed.subject, catalog, context.entities),
        )
    if len(candidates) > 1:
        return _response(
            request,
            KnowledgeAnswer(intent=parsed.intent, reason_code="ambiguous_subject"),
            "clarification",
            "问题对应多个主语, 请选择要查询的资产或实体。",
            candidates,
        )
    subject = next(iter(candidates))
    records, message = system_records(subject, parsed.intent, catalog, layer)
    claims, pending = document_claims(
        subject,
        parsed.intent,
        context,
        {item.asset_ref.asset_id for item in records},
        lambda identity, version: get_source_text(db, identity, version),
    )
    answered = bool(records or claims)
    knowledge = KnowledgeAnswer(
        intent=parsed.intent,
        subject=subject,
        system_records=records,
        system_message=message,
        claims=claims,
        pending_ambiguous_links=pending,
        reason_code=None if answered else "no_knowledge",
    )
    location = "在目录里" if subject.kind != "kg_entity" else "已解析为图谱实体"
    return _response(
        request,
        knowledge,
        "answered" if answered else "unanswerable",
        "系统记录与文档里的说法分别展示。"
        if answered
        else f"{subject.name} {location}, 但系统和文档都没有登记本题所需的记录。",
    )


def related_knowledge(db: Database, answer: AskAnswer, catalog: CatalogSnapshot) -> AskAnswer:
    """Attach at most five owner and upstream claims while preserving metric execution fields."""
    if answer.status != "answered" or answer.metric_card is None:
        return answer
    item = next(
        item
        for item in catalog.objects
        if item.asset_ref.asset_id == answer.metric_card.definition.id
    )
    subject = catalog_subject(item)
    claims, pending = document_claims(
        subject,
        "related",
        read_link_context(db),
        set(),
        lambda identity, version: get_source_text(db, identity, version),
    )
    if not claims and not pending:
        return answer
    return answer.model_copy(
        update={
            "knowledge": KnowledgeAnswer(
                intent="related",
                subject=subject,
                claims=claims[:5],
                pending_ambiguous_links=pending,
            )
        }
    )


def _response(
    request: AskRequest,
    knowledge: KnowledgeAnswer,
    status: Literal["answered", "unanswerable", "clarification"],
    message: str,
    candidates: tuple[KnowledgeSubject, ...] = (),
) -> AskAnswer:
    return AskAnswer(
        session_id=request.session_id or new_id(),
        question=request.question,
        reference_instant=request.reference_instant,
        answer_kind="knowledge",
        knowledge=knowledge,
        status=status,
        message=message,
        subject_candidates=candidates,
    )
