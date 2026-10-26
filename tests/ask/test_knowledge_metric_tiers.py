# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge and numeric identity resolution share registered-vocabulary precedence."""

import pytest

from datakeel.ask import service
from datakeel.ask.knowledge_parser import parse_knowledge_question
from datakeel.ask.parser import parse_question
from datakeel.ask.resolution import resolve_metric
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.metric_models import MetricCard, SemanticLayer, TermDefinition, TermTarget
from datakeel.metrics.projection import build_snapshot
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database
from datakeel.storage.metric_store import install_layer


def _conflicting_layer(layer: SemanticLayer, registered: str = "english_name") -> SemanticLayer:
    first = layer.metrics[0].model_copy(
        update={
            "id": "metric-a",
            "name": "指标甲",
            "english_name": None,
            "synonyms": [],
            "owner": "Fixture owner A",
        }
    )
    second = first.model_copy(
        update={
            "id": "metric-b",
            "name": "指标乙",
            "synonyms": ["Refund Value"],
            "owner": "Fixture owner B",
        }
    )
    terms: list[TermDefinition] = []
    if registered in {"name", "english_name"}:
        first = first.model_copy(update={registered: "Refund Value"})
    elif registered == "synonym":
        first = first.model_copy(update={"synonyms": ["Refund Value"]})
    else:
        terms = [
            TermDefinition(
                term="Refund Value" if registered == "term" else "Refund concept",
                synonyms=["Refund Value"] if registered == "term_synonym" else [],
                means=TermTarget(kind="metric", id=first.id),
            )
        ]
    return SemanticLayer(metrics=[first, second], terms=terms)


@pytest.mark.parametrize("registered", ["name", "english_name", "synonym", "term", "term_synonym"])
def test_registered_knowledge_metric_phrases_share_numeric_ambiguity(
    layer: SemanticLayer, registered: str
) -> None:
    """Canonical labels, English labels, aliases and glossary names cannot suppress peers."""
    modified = _conflicting_layer(layer, registered)
    catalog = build_snapshot(modified, CatalogSnapshot(scope="generated-fixture"))
    parsed = parse_knowledge_question("Who owns Refund Value?", catalog, modified)
    assert parsed is not None
    assert {item.asset_ref.asset_id for item in parsed.candidates} == {"metric-a", "metric-b"}
    assert parsed.recognition.rule_id == "K1-ambiguous-subject"
    numeric = resolve_metric(
        parse_question(AskRequest(question="Show Refund Value"), modified),
        [MetricCard(definition=item) for item in modified.metrics],
    )
    assert numeric.status == "clarification"
    assert {item.definition.id for item in numeric.candidates} == {"metric-a", "metric-b"}


@pytest.mark.parametrize("phrase", ["refund_value", "Refund Values"])
def test_registered_alias_outranks_literal_and_normalized_identifier_fallback(
    layer: SemanticLayer, phrase: str
) -> None:
    """Identifier spellings are a fallback in both routes, including a literal underscore ID."""
    modified = _conflicting_layer(layer).model_copy(update={"terms": []})
    first = modified.metrics[0].model_copy(
        update={"id": "refund_value", "english_name": None, "synonyms": []}
    )
    second = modified.metrics[1].model_copy(update={"synonyms": [phrase]})
    modified = modified.model_copy(update={"metrics": [first, second]})
    catalog = build_snapshot(modified, CatalogSnapshot(scope="generated-fixture"))
    parsed = parse_knowledge_question(f"Who owns {phrase}?", catalog, modified)
    assert parsed is not None
    assert [item.asset_ref.asset_id for item in parsed.candidates] == ["metric-b"]
    numeric = resolve_metric(
        parse_question(AskRequest(question=f"Show {phrase}"), modified),
        [MetricCard(definition=item) for item in modified.metrics],
    )
    assert numeric.status == "resolved"
    assert [item.definition.id for item in numeric.candidates] == ["metric-b"]


def test_english_name_and_alias_owner_conflict_returns_persisted_clarification(
    db: Database,
    enterprise_sample: EnterpriseSample,
    layer: SemanticLayer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conflicting labels cannot silently assert one of two different catalog owners."""
    install_layer(db, _conflicting_layer(layer))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("A conflicting owner request reached metric SQL execution")

    monkeypatch.setattr(service, "execute_query", forbidden)
    answer = ask_data(db, AskRequest(question="Who owns Refund Value?"))
    assert answer.answer_kind == "knowledge"
    assert answer.status == "clarification"
    assert {item.asset_ref.asset_id for item in answer.subject_candidates} == {
        "metric-a",
        "metric-b",
    }
    assert answer.knowledge is not None
    assert answer.knowledge.reason_code == "ambiguous_subject"
    assert answer.knowledge.subject is None
    assert answer.knowledge.system_records == ()
    assert answer.sql is None
    assert answer.result is None
    assert get_answer(db, answer.id) == answer
