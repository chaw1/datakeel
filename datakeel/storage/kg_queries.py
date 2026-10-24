# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read graph candidates, source locations and bounded display projections."""

from datakeel.core.errors import NotFoundError
from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_queries import (
    KGEntityView,
    KGGraph,
    KGQuery,
    KGQueryResult,
    KGRelationExplanation,
    KGRelationView,
    KGSourceText,
)
from datakeel.core.models import AssetRef
from datakeel.kg.text import normalize_name
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import read_assertions
from datakeel.storage.kg_context import KGContext, graph_events, read_context
from datakeel.storage.kg_graph import project_graph
from datakeel.storage.kg_store import get_job


def _matches(entity: KGEntity, query: KGQuery) -> bool:
    return (query.entity_type is None or entity.type == query.entity_type) and (
        query.name is None or normalize_name(query.name) in normalize_name(entity.name)
    )


def _assertion_matches(assertion: Assertion, query: KGQuery) -> bool:
    return (query.status is None or assertion.status == query.status) and (
        query.verification is None or assertion.verification == query.verification
    )


def _relation(assertion: Assertion, context: KGContext) -> KGRelationView | None:
    entities = {entity.asset_ref.asset_id: entity for entity in context.entities}
    if assertion.predicate == "kg.mentions" or not isinstance(assertion.object, AssetRef):
        return None
    if assertion.subject.asset_id not in entities or assertion.object.asset_id not in entities:
        return None
    event = next(
        (item for item in context.events if item.event_id == assertion.producer_event_id), None
    )
    return KGRelationView(
        assertion=assertion,
        head=entities[assertion.subject.asset_id],
        tail=entities[assertion.object.asset_id],
        extractor=str(event.params.get("kg_extractor", assertion.extractor.id))
        if event
        else assertion.extractor.id,
        model=str(event.params.get("kg_model", "unknown")) if event else "unknown",
        extraction_id=assertion.run_id,
    )


def _query(context: KGContext, query: KGQuery) -> KGQueryResult:
    entities = tuple(
        KGEntityView(
            **entity.model_dump(),
            mentions=tuple(
                item
                for item in context.assertions
                if item.predicate == "kg.mentions"
                and item.subject.asset_id == entity.asset_ref.asset_id
                and _assertion_matches(item, query)
            ),
        )
        for entity in context.entities
        if _matches(entity, query)
    )
    entities = tuple(
        entity.model_copy(update={"mention_count": len(entity.mentions)})
        for entity in entities
        if entity.mentions
    )
    relations = tuple(
        sorted(
            (
                relation
                for item in context.assertions
                if _assertion_matches(item, query)
                and (relation := _relation(item, context)) is not None
                and (_matches(relation.head, query) or _matches(relation.tail, query))
            ),
            key=lambda relation: (
                relation.assertion.verification != "needs_review",
                relation.assertion.id,
            ),
        )
    )
    return KGQueryResult(
        dataset_id=context.dataset_id,
        version_id=context.version_id,
        entities=tuple(
            sorted(entities, key=lambda entity: (entity.type, normalize_name(entity.name)))
        )[: query.limit],
        relations=relations[: query.limit],
        truncated=len(entities) > query.limit or len(relations) > query.limit,
    )


def query_kg(db: Database, query: KGQuery) -> KGQueryResult:
    """Filter one graph version and keep pending source checks first in relation results."""
    return _query(read_context(db, query), query)


def get_source_text(
    db: Database, file_id: str, version_id: str, extraction_id: str | None = None
) -> KGSourceText:
    """Read frozen normalized text, never a mutable current file path."""
    events = graph_events(db)
    identifiers = (
        (extraction_id,)
        if extraction_id
        else tuple(
            dict.fromkeys(
                str(event.params["run_id"])
                for event in reversed(events)
                if event.params.get("kg_version_id") == version_id
                and any(
                    ref.asset_id == file_id and ref.version == version_id for ref in event.inputs
                )
            )
        )
    )
    for identifier in identifiers:
        job = get_job(db, identifier)
        for document in job.prepared.documents:
            if document.asset_ref.asset_id == file_id and document.asset_ref.version == version_id:
                return KGSourceText(
                    asset_ref=document.asset_ref, filename=document.filename, text=document.text
                )
    msg = "Knowledge-graph source document was not found for the requested version"
    raise NotFoundError(msg)


def _summary(assertion: Assertion) -> str:
    if assertion.verification == "verified":
        return "Evidence, head entity and tail entity are located in the original source."
    detail = assertion.verification_detail
    if detail is None:
        return "Source verification is unavailable."
    descriptions = {
        "evidence": "the evidence quotation could not be verified",
        "head": "the head entity could not be located",
        "tail": "the tail entity could not be located",
    }
    reasons = tuple(
        dict.fromkeys(
            f"the {issue.role or 'relationship'} endpoint was not declared by the extractor"
            if issue.code == "endpoint_undeclared"
            else descriptions[issue.code]
            for issue in detail.issues
        )
    )
    return "Needs review: " + "; ".join(reasons) + "."


def explain_relation(db: Database, assertion_id: str) -> KGRelationExplanation:
    """Explain an exact relationship with every original document and missing check."""
    events = graph_events(db)
    with db.session() as session:
        assertion = next(
            (
                item
                for item in read_assertions(session, include_invalidated=True)
                if item.id == assertion_id
            ),
            None,
        )
    if assertion is None:
        msg = "Knowledge-graph relation was not found"
        raise NotFoundError(msg)
    event = next((item for item in events if item.event_id == assertion.producer_event_id), None)
    context = read_context(
        db,
        KGQuery(
            dataset_id=str(event.params["kg_dataset_id"]) if event else None,
            version_id=assertion.subject.version,
        ),
        include_invalidated=True,
    )
    relation = _relation(assertion, context)
    if relation is None:
        msg = "The assertion is not a graph relationship"
        raise NotFoundError(msg)
    refs = {(anchor.asset_ref.asset_id, anchor.asset_ref.version) for anchor in assertion.anchors}
    sources = tuple(
        get_source_text(db, file_id, version or "") for file_id, version in sorted(refs)
    )
    return KGRelationExplanation(relation=relation, sources=sources, summary=_summary(assertion))


def graph_kg(db: Database, query: KGQuery) -> KGGraph:
    """Merge accepted aliases for display while keeping rejected pairs separated."""
    context = read_context(db, query)
    return project_graph(_query(context, query), context.entities, context.assertions, query.limit)
