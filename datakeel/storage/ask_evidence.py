# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish question facts through the shared evidence artifact and event pipeline."""

from sqlalchemy.orm import Session

from datakeel.core.ask_models import AskAnswer, MatchEvidence
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import (
    Assertion,
    EvidenceAnchor,
    EvidenceValue,
    ExtractorRef,
    PredicateId,
    TextSpan,
    Whole,
)
from datakeel.core.knowledge_citations import knowledge_citations
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.core.question_models import QuestionProperties
from datakeel.metrics.projection import resolved_metric_cards
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.evidence_store import record_extraction_in_session

EXTRACTOR = ExtractorRef(id="evidence.ask", version="1.0")


def _term_ref(catalog: CatalogSnapshot, term_id: str) -> AssetRef:
    term = next(
        (
            item
            for item in catalog.objects
            if item.asset_ref.asset_type == "term" and item.asset_ref.asset_id == term_id
        ),
        None,
    )
    if term is None:
        msg = f"Question match references an unregistered term: {term_id}"
        raise ValidationError(msg)
    return term.asset_ref.model_copy(update={"version": str(term.revision)})


def _anchor(question: QuestionProperties, match: MatchEvidence | None = None) -> EvidenceAnchor:
    return EvidenceAnchor(
        asset_ref=question.asset_ref(),
        content_revision=question.content_revision,
        selector=TextSpan(start=match.start, end=match.end) if match else Whole(),
    )


def _facts(
    answer: AskAnswer, question: QuestionProperties, event_id: str, catalog: CatalogSnapshot
) -> tuple[Assertion, ...]:
    facts: list[Assertion] = []
    if answer.metric_card is not None:
        metric = answer.metric_card.definition
        facts.append(
            _assertion(
                question,
                event_id,
                "ask.answers_with",
                AssetRef(asset_type="metric", asset_id=metric.id, version=str(metric.version)),
                tuple(
                    _anchor(question, match)
                    for match in answer.matches
                    if match.metric_id == metric.id
                )
                or (_anchor(question),),
            )
        )
    if answer.answer_kind == "metric" and answer.status == "unanswerable":
        facts.append(
            _assertion(
                question,
                event_id,
                "ask.unanswerable",
                EvidenceValue(concept="metric", value="unknown"),
                (_anchor(question),),
            )
        )
    seen: set[tuple[str, int, int]] = set()
    for match in answer.matches:
        if match.term_id is None or (match.term_id, match.start, match.end) in seen:
            continue
        seen.add((match.term_id, match.start, match.end))
        facts.append(
            _assertion(
                question,
                event_id,
                "ask.matched_term",
                _term_ref(catalog, match.term_id),
                (_anchor(question, match),),
                match.source,
            )
        )
    facts.extend(
        _assertion(
            question,
            event_id,
            "ask.cites_assertion" if ref.asset_type == "assertion" else "ask.cites_asset",
            ref,
            (_anchor(question),),
        )
        for ref in knowledge_citations(answer.knowledge)
    )
    return tuple(facts)


def _assertion(
    question: QuestionProperties,
    event_id: str,
    kind: PredicateId,
    observed: AssetRef | EvidenceValue,
    anchors: tuple[EvidenceAnchor, ...],
    reason: str | None = None,
) -> Assertion:
    return Assertion(
        subject=question.asset_ref(),
        extractor=EXTRACTOR,
        producer_event_id=event_id,
        run_id=question.id,
        predicate=kind,
        object=observed,
        anchors=anchors,
        reason=reason,
    )


def _validate_metric(answer: AskAnswer, catalog: CatalogSnapshot) -> None:
    if answer.metric_card is None:
        return
    metric = answer.metric_card.definition
    current = next(
        (item for item in resolved_metric_cards(catalog) if item.definition.id == metric.id),
        None,
    )
    if current != answer.metric_card:
        msg = "Answer metric changed or disappeared before evidence publication; retry the question"
        raise ConflictError(msg)


def publish_answer_evidence(
    session: Session, answer: AskAnswer, question: QuestionProperties, actor: str
) -> tuple[str, tuple[Assertion, ...]]:
    """Bind all answer facts to one COMPLETE event and the shared rebuildable bundle."""
    catalog = read_snapshot(session)
    _validate_metric(answer, catalog)
    event_id = new_id()
    assertions = _facts(answer, question, event_id, catalog)
    references = [question.asset_ref()]
    references.extend(item.object for item in assertions if isinstance(item.object, AssetRef))
    event = LineageEvent(
        event_id=event_id,
        idempotency_key=f"ask:{answer.id}",
        event_type="COMPLETE",
        operator=EXTRACTOR.id,
        source_module="ask",
        on_behalf_of=actor,
        inputs=references,
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id=answer.id, version="1.0")],
        params={"run_id": answer.id},
    )
    record_extraction_in_session(
        session, event, KnowledgeBundle(run_id=answer.id, assertions=assertions)
    )
    return event_id, assertions
