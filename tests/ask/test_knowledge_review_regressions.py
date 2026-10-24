# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect independent review findings without using the sealed evaluation questions."""

from pathlib import Path

import pytest

from datakeel.ask import knowledge_service, service
from datakeel.ask.knowledge_parser import parse_knowledge_question
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import DimensionDefinition, TermDefinition, TermTarget
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.storage.database import Database
from datakeel.storage.link_queries import read_link_context
from tests.ask.knowledge_helpers import entity
from tests.ask.parsing_helpers import registered_context, registered_question


@pytest.mark.parametrize("vocabulary", ["column-term", "dimension-value"])
def test_registered_filter_vocabulary_cannot_erase_requested_owner(vocabulary: str) -> None:
    """A non-measure term or dimension value named owner is not a request for a metric value."""
    catalog, layer, context = registered_context("库存量")
    if vocabulary == "column-term":
        layer = layer.model_copy(
            update={
                "terms": [
                    TermDefinition(
                        term="负责人", means=TermTarget(kind="column", id="fixture/table/owner")
                    )
                ]
            }
        )
    else:
        layer = layer.model_copy(
            update={
                "dimensions": [
                    DimensionDefinition(
                        id="role", name="角色", column="fixture/role", values=["负责人"]
                    )
                ]
            }
        )
    parsed = parse_knowledge_question("库存量的负责人", catalog, layer, context)
    assert parsed is not None
    assert parsed.intent == "owner"
    assert parsed.recognition.focus == "person"
    assert parse_knowledge_question("按负责人看库存量", catalog, layer, context) is None


@pytest.mark.parametrize(
    ("metric", "name", "question"),
    [
        ("inventory_units", "Top inventory_units team", "Top inventory_units team负责哪些"),
        ("库存量", "最高库存量团队", "最高库存量团队负责哪些"),
    ],
)
def test_ranking_words_inside_longest_graph_name_are_not_numeric_cues(
    metric: str, name: str, question: str
) -> None:
    """An entity's registered name wins before its embedded words can imply quantity or ranking."""
    catalog, layer, _context = registered_context(metric)
    organization = entity("ranking-team", name, "organization")
    context = LinkContext(entities=(organization,))
    parsed = parse_knowledge_question(question, catalog, layer, context)
    assert parsed is not None
    assert parsed.intent == "owned"
    assert len(parsed.candidates) == 1
    assert parsed.candidates[0].asset_ref == organization.asset_ref
    assert parse_knowledge_question(f"How much {metric}?", catalog, layer, context) is None


@pytest.mark.parametrize(
    ("question", "subject"),
    [
        ("哪些表用库存量", "库存量"),
        ("库存量用于哪些表", "库存量"),
        ("What is inventory_units a source for?", "inventory_units"),
    ],
)
def test_source_subjects_keep_downstream_direction_across_use_and_source_for(
    question: str, subject: str
) -> None:
    """A metric serving as another asset's input must not return its own upstream."""
    parsed = registered_question(question, subject)
    assert parsed is not None
    assert parsed.intent == "downstream"
    assert parsed.recognition.direction == "downstream"


@pytest.mark.parametrize(
    "question",
    [
        "Who does Morgan report to?",
        "Which department does Morgan work for?",
        "Morgan在哪个部门工作",
    ],
)
def test_employment_and_reporting_questions_do_not_invent_asset_ownership(question: str) -> None:
    """A work affiliation question requests clarification instead of listing owned assets."""
    parsed = registered_question(question, "Morgan")
    assert parsed is not None
    assert parsed.intent == "related"
    assert parsed.intent_candidates == ("owned", "owner")


def test_work_context_does_not_erase_an_explicit_owned_metric_question() -> None:
    """Mentioning work context does not turn a request for owned metrics into job affiliation."""
    parsed = registered_question("Morgan工作中负责哪些指标", "Morgan")
    assert parsed is not None
    assert parsed.intent == "owned"
    assert parsed.intent_candidates == ()


@pytest.mark.parametrize("question", ["周岩负责哪些", "出货额"])
def test_one_graph_snapshot_binds_subject_and_claims_for_the_whole_answer(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, question: str
) -> None:
    """A graph publication between potential reads cannot mix subject and claim versions."""
    seed_enterprise_kg(db, tmp_path)
    initial = read_link_context(db)
    person = next(item for item in initial.entities if item.name == "周岩")
    changed_person = person.model_copy(
        update={"asset_ref": person.asset_ref.model_copy(update={"version": "next-graph-version"})}
    )
    changed = initial.model_copy(
        update={
            "entities": tuple(
                changed_person if item == person else item for item in initial.entities
            ),
            "assertions": tuple(
                item.model_copy(update={"subject": changed_person.asset_ref})
                if item.subject == person.asset_ref
                else item
                for item in initial.assertions
            ),
        }
    )
    reads: list[LinkContext] = []

    def next_graph(_db: Database) -> LinkContext:
        context = initial if not reads else changed
        reads.append(context)
        return context

    monkeypatch.setattr(service, "read_link_context", next_graph)
    monkeypatch.setattr(knowledge_service, "read_link_context", next_graph)
    answer = ask_data(db, AskRequest(question=question))
    assert answer.status == "answered"
    assert len(reads) == 1
    assert answer.knowledge is not None
    assert answer.knowledge.claims
    assert all(
        claim.head.asset_ref.version != "next-graph-version" for claim in answer.knowledge.claims
    )
