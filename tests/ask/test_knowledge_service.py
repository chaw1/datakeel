# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Question integration preserves old metric results and bounds optional document context."""

from pathlib import Path

import pytest

from datakeel.ask import knowledge_service
from datakeel.ask.knowledge_service import related_knowledge
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.kg_queries import KGSourceText
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.metrics.projection import build_snapshot
from datakeel.ontology.catalog_functions import invoke_catalog
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database
from tests.ask.knowledge_helpers import claim_context, source_reader
from tests.ask.test_models import answered_fixture


def test_knowledge_clarification_pins_only_candidates_and_no_fact_refusals_explain_scope(
    db: Database,
    enterprise_sample: EnterpriseSample,
) -> None:
    """Candidate selection does not become an arbitrary subject override."""
    request = AskRequest(question="营业额谁负责")
    ambiguous = ask_data(db, request)
    assert ambiguous.answer_kind == "knowledge"
    assert ambiguous.status == "clarification"
    selected = ask_data(db, request.model_copy(update={"subject_id": "sales_amount"}))
    assert selected.status == "answered"
    assert selected.knowledge is not None
    assert selected.knowledge.subject is not None
    assert selected.knowledge.subject.asset_ref.asset_id == "sales_amount"
    assert get_answer(db, selected.id) == selected
    bad = ask_data(db, request.model_copy(update={"subject_id": "customer_count"}))
    assert bad.status == "unanswerable"
    assert bad.knowledge is not None
    assert bad.knowledge.reason_code == "unknown_subject"
    empty = ask_data(db, AskRequest(question="warranties 表谁负责"))
    assert empty.status == "unanswerable"
    assert empty.knowledge is not None
    assert empty.knowledge.reason_code == "no_knowledge"
    assert empty.subject_candidates == ()
    assert "在目录里" in empty.message


def test_numeric_answers_without_graph_context_remain_compact(
    db: Database,
    enterprise_sample: EnterpriseSample,
) -> None:
    """A pure catalog answer does not acquire empty context or redundant audit assertions."""
    answer = ask_data(db, AskRequest(question="出货额"))
    assert answer.answer_kind == "metric"
    assert answer.status == "answered"
    assert answer.knowledge is None
    assert not any(item.predicate.startswith("ask.cites_") for item in answer.assertions)
    result = invoke_catalog(db, "ask_data", JsonDocument({"question": "出货额"}))
    assert isinstance(result.data, dict)
    assert not {"answer_kind", "knowledge", "subject_candidates"}.intersection(result.data)
    assert AskAnswer.model_validate(result.data).answer_kind == "metric"


def test_related_document_context_is_limited_to_five_without_changing_query(
    db: Database,
    layer: SemanticLayer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long graph cannot make the metric response lose its numerical contract or size bound."""
    answer = answered_fixture(layer)
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    _subject, context = claim_context()
    assert answer.metric_card is not None
    metric_ref = AssetRef(
        asset_type="metric", asset_id=answer.metric_card.definition.id, version="1"
    )
    link = context.links[0].model_copy(
        update={"target": context.links[0].target.model_copy(update={"asset_ref": metric_ref})}
    )
    claims = tuple(
        context.assertions[1].model_copy(update={"id": f"owner-{index}"}) for index in range(7)
    )
    context = context.model_copy(update={"links": (link,), "assertions": claims})

    def context_reader(_db: Database) -> LinkContext:
        return context

    def read_source(_db: Database, identity: str, version: str) -> KGSourceText:
        return source_reader(identity, version)

    monkeypatch.setattr(knowledge_service, "read_link_context", context_reader)
    monkeypatch.setattr(knowledge_service, "get_source_text", read_source)
    result = related_knowledge(db, answer, catalog)
    assert result.knowledge is not None
    assert len(result.knowledge.claims) == 5
    assert result.result == answer.result
    assert result.sql == answer.sql
    assert result.metric_card == answer.metric_card


def test_bilingual_knowledge_tool_result_has_complete_assertion_citations(
    db: Database,
    tmp_path: Path,
) -> None:
    """The production recording produces exact link and relation audit receipts through ask_data."""
    seed_enterprise_kg(db, tmp_path)
    answer = ask_data(db, AskRequest(question="What is inventory_units derived from?"))
    assert answer.status == "answered"
    assert answer.knowledge is not None
    assert answer.knowledge.claims[0].consistency == "not_in_catalog"
    cited = {
        item.object.asset_id
        for item in answer.assertions
        if item.predicate == "ask.cites_assertion" and isinstance(item.object, AssetRef)
    }
    for claim in answer.knowledge.claims:
        assert claim.assertion_id in cited
        assert claim.subject_link is not None
        assert claim.subject_link.assertion_id in cited
    assert get_answer(db, answer.id) == answer
