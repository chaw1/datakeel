# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assemble knowledge answers and bounded related claims without model or SQL calls."""

from typing import Literal

from datakeel.ask.knowledge_claims import SourceReader, document_claims
from datakeel.ask.knowledge_parser import KnowledgeQuestion
from datakeel.ask.knowledge_subjects import catalog_subject, subject_candidates, subject_suggestions
from datakeel.ask.knowledge_system import system_records
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.errors import NotFoundError
from datakeel.core.evidence_models import EvidenceAnchor
from datakeel.core.kg_queries import KGSourceText
from datakeel.core.knowledge_models import KnowledgeAnswer, KnowledgeIntent, KnowledgeSubject
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import new_id
from datakeel.storage.database import Database
from datakeel.storage.link_queries import read_link_context


def knowledge_answer(
    db: Database,
    request: AskRequest,
    parsed: KnowledgeQuestion,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
) -> AskAnswer:
    """Resolve one subject and retain separate catalog and document sections for every state."""
    if parsed.unsupported_phrasing:
        return _response(
            request,
            KnowledgeAnswer(intent=parsed.intent, reason_code="unsupported_phrasing"),
            "unanswerable",
            "这是知识类问题, 但暂时无法确定主语和关系。"
            "请明确资产或实体, 以及负责人、上游或下游关系。",
        )
    context = read_link_context(db)
    candidates = subject_candidates(
        parsed.subject,
        catalog,
        layer,
        context.entities,
        links=context.links,
        entity_sources=context.entity_sources,
    )
    pinned = request.subject_id or request.metric_id
    if pinned:
        candidates = tuple(item for item in candidates if item.asset_ref.asset_id == pinned)
    if not candidates:
        return _response(
            request,
            KnowledgeAnswer(intent=parsed.intent, reason_code="unknown_subject"),
            "unanswerable",
            "无法定位主语。以下是最接近的指标、表或图谱实体。",
            subject_suggestions(
                parsed.subject, catalog, context.entities, entity_sources=context.entity_sources
            ),
        )
    if len(candidates) > 1:
        return _response(
            request,
            KnowledgeAnswer(intent=parsed.intent, reason_code="ambiguous_subject"),
            "clarification",
            "问题对应多个主语, 请选择要查询的资产或实体。",
            candidates,
        )
    knowledge = _resolved_knowledge(next(iter(candidates)), parsed.intent, context, catalog, layer)
    return _response(
        request,
        knowledge,
        "answered" if knowledge.reason_code is None else "unanswerable",
        _knowledge_message(knowledge),
    )


def _resolved_knowledge(
    subject: KnowledgeSubject,
    intent: KnowledgeIntent,
    context: LinkContext,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
) -> KnowledgeAnswer:
    records, message = system_records(subject, intent, catalog, layer)
    claims, pending = document_claims(
        subject,
        intent,
        context,
        {item.asset_ref.asset_id for item in records},
        _source_reader(context),
    )
    return KnowledgeAnswer(
        intent=intent,
        subject=subject,
        system_records=records,
        system_message=message,
        claims=claims,
        pending_ambiguous_links=pending,
        reason_code=None if records or claims else "pending_links" if pending else "no_knowledge",
    )


def _knowledge_message(knowledge: KnowledgeAnswer) -> str:
    if knowledge.reason_code is None:
        return "系统记录与文档里的说法分别展示。"
    if knowledge.pending_ambiguous_links:
        return f"有 {knowledge.pending_ambiguous_links} 条文档说法的关联待确认。"
    subject = knowledge.subject
    location = "在目录里" if subject and subject.kind != "kg_entity" else "已解析为图谱实体"
    name = subject.name if subject else "主语"
    return f"{name} {location}, 但系统和文档都没有登记本题所需的记录。"


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
    context = read_link_context(db)
    claims, pending = document_claims(
        subject,
        "related",
        context,
        set(),
        _source_reader(context),
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


def _source_reader(context: LinkContext) -> SourceReader:
    sources = {
        (
            document.asset_ref.asset_id,
            document.asset_ref.version,
            document.content_revision,
        ): KGSourceText(
            asset_ref=document.asset_ref, filename=document.filename, text=document.text
        )
        for document in context.documents
    }

    def read_source(anchor: EvidenceAnchor) -> KGSourceText:
        source = sources.get(
            (anchor.asset_ref.asset_id, anchor.asset_ref.version, anchor.content_revision)
        )
        if source is None:
            msg = "Knowledge source revision is not available in the current graph context"
            raise NotFoundError(msg)
        return source

    return read_source


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
