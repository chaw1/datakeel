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
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.kg_execution import KGDocument
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
from tests.ask.knowledge_helpers import ANCHOR, SOURCE, claim_context
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


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("missing_revision", [False, True])
def test_related_document_context_is_limited_to_five_without_changing_query(
    db: Database,
    layer: SemanticLayer,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reverse: bool,
    missing_revision: bool,
) -> None:
    """Bound claims without changing metric output, and never quote a different file revision."""
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
    original = KGDocument(
        asset_ref=SOURCE.asset_ref,
        filename=SOURCE.filename,
        text=SOURCE.text,
        content_revision=ANCHOR.content_revision,
        blocks=(),
    )
    other_revision = original.model_copy(update={"content_revision": "b" * 64, "text": "Different"})
    documents = (original, other_revision) if reverse else (other_revision, original)
    if missing_revision:
        documents = (other_revision,)
    context = context.model_copy(
        update={"links": (link,), "assertions": claims, "documents": documents}
    )

    def context_reader(_db: Database) -> LinkContext:
        return context

    monkeypatch.setattr(knowledge_service, "read_link_context", context_reader)
    result = related_knowledge(db, answer, catalog)
    if missing_revision:
        assert result == answer
        assert result.knowledge is None
        return
    assert result.knowledge is not None
    assert len(result.knowledge.claims) == 5
    assert {claim.evidence[0].text for claim in result.knowledge.claims} == {SOURCE.text[:32]}
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


def test_related_context_skips_missing_source_without_discarding_available_claims(
    db: Database, layer: SemanticLayer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing optional document cannot suppress a metric result or another valid citation."""
    answer = answered_fixture(layer)
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    _subject, context = claim_context()
    assert answer.metric_card is not None
    link = context.links[0]
    link = link.model_copy(
        update={
            "target": link.target.model_copy(
                update={
                    "asset_ref": AssetRef(
                        asset_type="metric", asset_id=answer.metric_card.definition.id, version="1"
                    )
                }
            )
        }
    )
    available = context.assertions[1]
    missing = available.model_copy(
        update={
            "id": "missing-document-claim",
            "anchors": (ANCHOR.model_copy(update={"content_revision": "b" * 64}),),
        }
    )
    context = context.model_copy(
        update={
            "links": (link,),
            "assertions": (missing, available),
            "documents": (
                KGDocument(
                    asset_ref=SOURCE.asset_ref,
                    filename=SOURCE.filename,
                    text=SOURCE.text,
                    content_revision=ANCHOR.content_revision,
                    blocks=(),
                ),
            ),
        }
    )

    def frozen_link_context(_db: Database) -> LinkContext:
        return context

    monkeypatch.setattr(knowledge_service, "read_link_context", frozen_link_context)
    result = related_knowledge(db, answer, catalog)
    assert result.knowledge is not None
    assert tuple(claim.assertion_id for claim in result.knowledge.claims) == (available.id,)
    assert result.result == answer.result
    assert result.sql == answer.sql
    assert result.metric_card == answer.metric_card


def test_answer_sources_reuse_current_graph_documents_without_event_rescans(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metric context and knowledge claims read sources from the already-loaded frozen graph."""
    seed_enterprise_kg(db, tmp_path)

    def unexpected_source_read(
        _db: Database,
        _identity: str,
        _version: str,
        _extraction_id: str | None = None,
        *,
        access: AccessContext | None = None,
    ) -> KGSourceText:
        pytest.fail("A current graph source must not rescan extraction history")

    monkeypatch.setattr("datakeel.storage.kg_queries.get_source_text", unexpected_source_read)
    for question in ("出货额", "出货额谁负责"):
        answer = ask_data(db, AskRequest(question=question))
        assert answer.status == "answered"
        assert answer.knowledge is not None
        assert answer.knowledge.claims
        assert all(claim.evidence for claim in answer.knowledge.claims)
