# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply the reproducible enterprise reviews and verify re-extraction inheritance."""

from datakeel.core.evidence_models import AssertionDecisionRequest, AssertionStatus
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.kg_queries import KGQuery
from datakeel.harness.enterprise_kg import extract_enterprise_documents
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.kg_queries import query_kg
from datakeel.storage.link_queries import list_links
from datakeel.storage.link_store import relink


def review_enterprise_kg(db: Database, fixture: CaseFixture) -> None:
    """Review four assertions, relink, and replay the same dataset version in that order."""
    graph = query_kg(db, KGQuery(dataset_id=fixture.dataset_id, limit=500))
    decisions: tuple[tuple[str, str, AssertionStatus], ...] = (
        ("周岩", "出货额", "accepted"),
        ("韩露", "零售额", "rejected"),
    )
    for head, tail, status in decisions:
        relation = next(
            item
            for item in graph.relations
            if item.head.name == head
            and item.tail.name == tail
            and item.assertion.predicate == "kg.owns"
        )
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(relation.assertion.id,),
                status=status,
                actor="enterprise-reviewer",
                reason="Scripted human review of a fictional enterprise fixture",
                idempotency_key=f"enterprise-review:{relation.assertion.id}",
            ),
        )
    for link in list_links(db, fixture.dataset_id):
        if link.entity.name != "营业额":
            continue
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(link.assertion.id,),
                status="accepted" if link.target.name == "销售额" else "rejected",
                actor="enterprise-reviewer",
                reason="Resolve the fictional turnover alias to sales",
                idempotency_key=f"enterprise-review:{link.assertion.id}",
            ),
        )
    relink(db)
    extract_enterprise_documents(db, fixture)
