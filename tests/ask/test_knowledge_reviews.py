# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persisted reviews and same-name identities preserve metric and knowledge behavior."""

from pathlib import Path

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.metrics.projection import semantic_layer
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.link_queries import list_links
from datakeel.storage.metric_store import install_layer


def _reject(db: Database, assertion_id: str) -> None:
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(assertion_id,),
            status="rejected",
            actor="fixture-reviewer",
            idempotency_key=f"reject-{assertion_id}",
        ),
    )


def test_same_named_catalog_role_and_person_answer_with_system_and_document_facts(
    db: Database, tmp_path: Path
) -> None:
    """A namesake is one subject whose registered role and document evidence both remain visible."""
    seed_enterprise_kg(db, tmp_path)
    with db.session() as session:
        snapshot = read_snapshot(session)
    layer = semantic_layer(snapshot)
    renamed = layer.model_copy(
        update={
            "metrics": [
                item.model_copy(update={"owner": "周岩"}) if item.owner == "供应链负责人" else item
                for item in layer.metrics
            ]
        }
    )
    install_layer(db, renamed)
    answer = ask_data(db, AskRequest(question="周岩负责哪些指标"))
    assert answer.status == "answered"
    assert answer.subject_candidates == ()
    assert answer.knowledge is not None
    assert answer.knowledge.subject is not None
    assert answer.knowledge.subject.kind == "owner"
    assert {item.asset_ref.asset_id for item in answer.knowledge.system_records} == {
        "shipment_amount",
        "shipment_units",
    }
    assert answer.knowledge.claims
    assert all(claim.head.name == "周岩" for claim in answer.knowledge.claims)
    assert all(claim.evidence for claim in answer.knowledge.claims)


def test_rejected_graph_association_keeps_numeric_answer_and_distinguishes_knowledge_subjects(
    db: Database, tmp_path: Path
) -> None:
    """A rejected graph identity changes clarification without changing metric execution."""
    seed_enterprise_kg(db, tmp_path)
    before = ask_data(db, AskRequest(question="出货额"))
    link = next(
        link
        for link in list_links(db)
        if link.entity.name == "出货额" and link.target.asset_ref.asset_id == "shipment_amount"
    )
    _reject(db, link.assertion.id)
    numeric = ask_data(db, AskRequest(question="出货额"))
    assert numeric.answer_kind == "metric"
    assert numeric.status == "answered"
    assert numeric.result == before.result
    assert numeric.sql == before.sql
    assert numeric.metric_card == before.metric_card
    knowledge = ask_data(db, AskRequest(question="出货额谁负责"))
    assert knowledge.answer_kind == "knowledge"
    assert knowledge.status == "clarification"
    assert knowledge.result is None
    assert {item.kind for item in knowledge.subject_candidates} == {"metric", "kg_entity"}
    document = next(item for item in knowledge.subject_candidates if item.kind == "kg_entity")
    assert document.dataset_name


def test_rejected_competing_match_leaves_a_pending_confirmation_claim(
    db: Database, tmp_path: Path
) -> None:
    """An actual persisted rejection reduces ambiguity without silently accepting the survivor."""
    seed_enterprise_kg(db, tmp_path)
    before = ask_data(db, AskRequest(question="Grace Liu 负责哪些"))
    assert before.knowledge is not None
    assert before.knowledge.pending_ambiguous_links == 1
    competitor = next(
        link
        for link in list_links(db)
        if link.entity.name == "营业额" and link.target.name == "零售额"
    )
    _reject(db, competitor.assertion.id)
    answer = ask_data(db, AskRequest(question="Grace Liu 负责哪些"))
    assert answer.status == "answered"
    assert answer.knowledge is not None
    assert answer.knowledge.pending_ambiguous_links == 0
    assert len(answer.knowledge.claims) == 1
    claim = answer.knowledge.claims[0]
    assert claim.other_end.status == "linked"
    assert claim.other_end.asset_name == "销售额"
    assert claim.other_end.link_status == "candidate"
