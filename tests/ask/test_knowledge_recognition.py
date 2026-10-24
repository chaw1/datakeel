# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check subject-first semantics at boundaries independent of the evaluation corpora."""

import pytest

from datakeel.ask.knowledge_parser import parse_knowledge_question
from datakeel.ask.knowledge_subjects import subject_candidates
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.evidence_models import EvidenceAnchor, TextSpan
from datakeel.core.kg_execution import KGDocument
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import DimensionDefinition, SemanticLayer
from tests.ask.knowledge_helpers import SOURCE, assertion, entity
from tests.ask.parsing_helpers import registered_context, registered_question


@pytest.mark.parametrize(
    ("question", "subject", "intent"),
    [
        ("库存量被谁维护?", "库存量", "owner"),
        ("库存量被哪张表生成?", "库存量", "upstream"),
        ("Who used inventory_units?", "inventory_units", "downstream"),
        ("谁曾用过库存量?", "库存量", "downstream"),
        ("What are the tables behind inventory_units?", "inventory_units", "upstream"),
        ("What is the team responsible for inventory_units?", "inventory_units", "owner"),
        ("哪些指标对应orders的数据表?", "orders", "downstream"),
        ("Which tables are used by orders?", "orders", "upstream"),
        ("被orders使用的表有哪些?", "orders", "upstream"),
        ("被哪些表使用的orders?", "orders", "downstream"),
        ("库存量取了哪两张表?", "库存量", "upstream"),
        ("库存量用哪种表?", "库存量", "upstream"),
        ("哪三位同事处理库存量?", "库存量", "owner"),
        ("Which three tables supply inventory_units?", "inventory_units", "upstream"),
    ],
)
def test_focus_and_voice_follow_grammatical_roles(question: str, subject: str, intent: str) -> None:
    """Passive ownership and fronted source clauses must not invert dependency direction."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == intent
    assert parsed.recognition.rule_id
    assert parsed.recognition.subjects


@pytest.mark.parametrize("question", ["库存量的负责人", "库存量按哪些表加工"])
def test_dimension_names_cannot_swallow_knowledge_focus(question: str) -> None:
    """A registered owner dimension is only a grouping when grouping syntax is present."""
    catalog, layer, context = registered_context("库存量")
    layer = layer.model_copy(
        update={
            "dimensions": [
                DimensionDefinition(
                    id="owner",
                    name="负责人",
                    column="fixture/owner",
                    values=["北区"],
                )
            ]
        }
    )
    parsed = parse_knowledge_question(question, catalog, layer, context)
    assert parsed is not None
    assert parsed.recognition.focus in {"person", "table"}
    assert parse_knowledge_question("各负责人库存量", catalog, layer, context) is None


def test_longest_graph_names_normalize_mixed_spacing_and_never_split_words() -> None:
    """Long names consume contained table tokens; unknown identifier suffixes stay unknown."""
    catalog, layer, _ = registered_context("sales")
    graph = entity("ops", "Sales Ops team", "organization")
    found = subject_candidates("What does the Sales Ops team own?", catalog, layer, (graph,))
    assert len(found) == 1
    assert found[0].asset_ref == graph.asset_ref
    mixed = entity("team", "orders 团队", "organization")
    assert subject_candidates("orders团队负责哪些", catalog, layer, (mixed,))[0].name == mixed.name
    assert subject_candidates("sales_clean谁负责", catalog, layer, ()) == ()
    assert subject_candidates("main.sales_clean谁负责", catalog, layer, ()) == ()


def test_two_registered_subjects_clarify_and_single_type_lists_need_direction() -> None:
    """Multiple names are not guessed, while same-type lists offer direction choices."""
    catalog, layer, _ = registered_context("orders")
    graph = entity("report", "日报", "dataset")
    parsed = parse_knowledge_question(
        "orders与日报有哪些关系", catalog, layer, LinkContext(entities=(graph,))
    )
    assert parsed is not None
    assert len(parsed.candidates) == 2
    assert parsed.recognition.rule_id == "K1-ambiguous-subject"
    unresolved = parse_knowledge_question("orders对应哪些表", catalog, layer)
    assert unresolved is not None
    assert unresolved.intent_candidates == ("upstream", "downstream")
    unknown = parse_knowledge_question(
        "未登记资产是哪个组照看的", CatalogSnapshot(scope="empty"), SemanticLayer()
    )
    assert unknown is not None
    assert unknown.recognition.rule_id == "K0-unknown-subject"


def test_graph_mention_aliases_resolve_only_their_own_evidence_spans() -> None:
    """A verified mention is a spelling of its entity, never of the surrounding sentence."""
    person = entity("canonical", "Morgan Smith", "person")
    anchor = EvidenceAnchor(
        asset_ref=SOURCE.asset_ref, content_revision="a" * 64, selector=TextSpan(start=33, end=39)
    )
    mention = assertion("mention", person.asset_ref, "kg.mentions", SOURCE.asset_ref).model_copy(
        update={"anchors": (anchor,)}
    )
    context = LinkContext(
        entities=(person,),
        assertions=(mention,),
        documents=(
            KGDocument(
                asset_ref=SOURCE.asset_ref,
                filename=SOURCE.filename,
                text=SOURCE.text,
                content_revision="a" * 64,
                blocks=(),
            ),
        ),
    )
    parsed = parse_knowledge_question(
        "What does Morgan own?", CatalogSnapshot(scope="empty"), SemanticLayer(), context
    )
    assert parsed is not None
    assert parsed.intent == "owned"
    assert parsed.candidates[0].name == "Morgan Smith"
    unrelated = parse_knowledge_question(
        "Who owns orders?", CatalogSnapshot(scope="empty"), SemanticLayer(), context
    )
    assert unrelated is not None
    assert unrelated.candidates == ()
