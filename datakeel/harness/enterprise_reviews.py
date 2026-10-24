# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply the reproducible enterprise reviews and verify re-extraction inheritance."""

from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.kg_queries import KGQuery
from datakeel.core.knowledge_reviews import KnowledgeReviews
from datakeel.harness.enterprise_kg import extract_enterprise_documents
from datakeel.harness.resources import contract_path
from datakeel.kg.loader import load_contract
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.kg_queries import query_kg
from datakeel.storage.link_queries import list_links
from datakeel.storage.link_store import relink


def review_enterprise_kg(db: Database, fixture: CaseFixture) -> None:
    """Review four assertions, relink, and replay the same dataset version in that order."""
    graph = query_kg(db, KGQuery(dataset_id=fixture.dataset_id, limit=500))
    reviews = load_contract(contract_path("ask/enterprise-reviews.yaml"), KnowledgeReviews)
    for review in reviews.relations:
        relation = next(
            item
            for item in graph.relations
            if item.head.name == review.head
            and item.tail.name == review.tail
            and item.assertion.predicate == review.predicate
        )
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(relation.assertion.id,),
                status=review.status,
                actor="enterprise-reviewer",
                reason=review.reason,
                idempotency_key=f"enterprise-review:{relation.assertion.id}",
            ),
        )
    links = list_links(db, fixture.dataset_id)
    for review in reviews.links:
        link = next(
            item
            for item in links
            if item.entity.name == review.entity and item.target.name == review.target
        )
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(link.assertion.id,),
                status=review.status,
                actor="enterprise-reviewer",
                reason=review.reason,
                idempotency_key=f"enterprise-review:{link.assertion.id}",
            ),
        )
    relink(db)
    extract_enterprise_documents(db, fixture)
