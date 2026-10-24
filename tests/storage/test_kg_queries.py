# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read graph facts from event metadata and existing assertion projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core import predicate_registry
from datakeel.core.errors import NotFoundError
from datakeel.core.evidence_models import VerificationDetail, VerificationIssue
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import new_id, utcnow
from datakeel.storage.events import append_event
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.kg_context import graph_events
from datakeel.storage.kg_queries import explain_relation, get_source_text, graph_kg, query_kg
from tests.kg.helpers import graph_product, seed_graph

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_graph_queries_empty_and_explicit_missing_scopes_are_typed(db: Database) -> None:
    """An empty selection never invents entities or a different dataset scope."""
    assert query_kg(db, KGQuery()).entities == ()
    result = query_kg(db, KGQuery(dataset_id="missing", version_id="missing-version"))
    assert result.dataset_id == "missing"
    assert result.version_id == "missing-version"
    assert graph_kg(db, KGQuery()).nodes == ()


def test_queries_filter_mentions_relations_and_put_needs_review_first(db: Database) -> None:
    """Name, type, status and verification filters preserve bounded single-version results."""
    good, source = graph_product("Acme", "good")
    seed_graph(db, good, source)
    bad, other = graph_product("Beta", "bad", missing=True)
    assertions = seed_graph(db, bad, other)
    result = query_kg(db, KGQuery())
    assert result.dataset_id == "dataset"
    assert result.relations[0].assertion.verification == "needs_review"
    assert len(result.relations) == 2
    assert all(entity.mention_count == len(entity.mentions) for entity in result.entities)
    assert len(query_kg(db, KGQuery(name="acme")).relations) == 1
    assert len(query_kg(db, KGQuery(entity_type="organization")).entities) == 2
    assert len(query_kg(db, KGQuery(verification="needs_review")).relations) == 1
    assert query_kg(db, KGQuery(limit=1)).truncated
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    with db.session() as session:
        row = session.get(AssertionRow, relation.id)
        assert row is not None
        row.status = "accepted"
        session.commit()
    assert query_kg(db, KGQuery(status="accepted")).relations[0].assertion.id == relation.id
    assert query_kg(db, KGQuery(status="rejected")).relations == ()
    assert graph_kg(db, KGQuery(limit=1)).truncated


def test_explanation_reports_missing_tail_and_reads_frozen_source(db: Database) -> None:
    """The explanation names the failed check rather than treating a real quotation as enough."""
    product, source = graph_product(missing=True)
    assertions = seed_graph(db, product, source)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    explanation = explain_relation(db, relation.id)
    assert "tail entity could not be located" in explanation.summary
    assert explanation.sources[0].text == source.text
    assert explanation.relation.model == "fixture-model"
    assert get_source_text(db, "document", "version", "run-document").text == source.text
    with pytest.raises(NotFoundError):
        get_source_text(db, "document", "wrong-version")
    with pytest.raises(NotFoundError):
        get_source_text(db, "missing", "version", "run-document")
    with pytest.raises(NotFoundError):
        explain_relation(db, "missing")
    mention = next(item for item in assertions if item.predicate == "kg.mentions")
    with pytest.raises(NotFoundError, match="not a graph relationship"):
        explain_relation(db, mention.id)


def test_cold_registry_restores_custom_vocabulary_before_assertion_parsing(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen event schemas make reads independent of prior extraction in this process."""
    product, source = graph_product()
    seed_graph(db, product, source)
    monkeypatch.setattr(
        predicate_registry,
        "_PREDICATES",
        {
            item.id: item
            for item in predicate_registry.registered_predicates()
            if item.id != "kg.uses"
        },
    )
    assert query_kg(db, KGQuery()).relations[0].assertion.predicate == "kg.uses"


def test_summary_distinguishes_undeclared_endpoint_from_missing_spelling(db: Database) -> None:
    """Endpoint synthesis remains explicit even when all three source positions exist."""
    product, source = graph_product()
    drafts = tuple(
        draft.model_copy(
            update={
                "verification": "needs_review",
                "verification_detail": VerificationDetail(
                    issues=(VerificationIssue(code="endpoint_undeclared", role="tail"),)
                ),
            }
        )
        if draft.predicate == "kg.uses"
        else draft
        for draft in product.drafts
    )
    assertions = seed_graph(db, product.model_copy(update={"drafts": drafts}), source)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    assert "tail endpoint was not declared" in explain_relation(db, relation.id).summary


def test_verified_and_unavailable_explanations_are_explicit(db: Database) -> None:
    """Optional legacy verification never implies a successful source check."""
    product, source = graph_product()
    assertions = seed_graph(db, product, source)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    assert "located in the original" in explain_relation(db, relation.id).summary
    legacy, other = graph_product("Legacy", "legacy")
    drafts = tuple(
        draft.model_copy(update={"verification": None, "verification_detail": None})
        for draft in legacy.drafts
    )
    assertions = seed_graph(db, legacy.model_copy(update={"drafts": drafts}), other)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    assert "unavailable" in explain_relation(db, relation.id).summary


def test_retained_source_falls_back_to_its_original_frozen_job(db: Database) -> None:
    """A later extraction references retained documents without copying their private text."""
    first, source = graph_product("Acme", "first")
    seed_graph(db, first, source)
    second, other = graph_product("Beta", "second")
    seed_graph(db, second, other)
    event = graph_events(db)[-1].model_copy(
        update={
            "event_id": new_id(),
            "idempotency_key": new_id(),
            "occurred_at": utcnow(),
            "inputs": [source.file, other.file],
        }
    )
    with db.session() as session:
        append_event(session, event)
        session.commit()
    assert get_source_text(db, "first", "version").text == source.text
