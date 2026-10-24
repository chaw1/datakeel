# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize declared categories and account for unknown entity and relation claims."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.loader import get_schema
from datakeel.storage.kg_store import get_job
from tests.kg.helpers import graph_product
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("spelling", ["Organization", " Organization ", "ORGANIZATION"])
def test_entity_type_case_and_whitespace_produce_the_canonical_graph(spelling: str) -> None:
    """Formatting variations preserve the same entity identity, mentions and relation evidence."""
    expected, source = graph_product()
    raw = pair_result().output.model_copy(
        update={
            "entities": (
                ExtractedEntity(name="Acme", type=spelling),
                ExtractedEntity(name="Widget", type="\tSYSTEM\n"),
            )
        }
    )
    assert assemble_extraction(raw, get_schema(), source) == expected


@pytest.mark.parametrize("spelling", ["company", " Company "])
def test_unknown_entity_and_its_relation_are_counted_with_the_correct_reason(spelling: str) -> None:
    """Unknown declarations remain visible and cannot be mistaken for a domain/range mismatch."""
    _, source = graph_product()
    raw = pair_result().output.model_copy(
        update={
            "entities": (
                ExtractedEntity(name="Acme", type=spelling),
                ExtractedEntity(name="Widget", type="system"),
            )
        }
    )
    product = assemble_extraction(raw, get_schema(), source)
    assert [entity.name for entity in product.entities] == ["Widget"]
    assert all(draft.predicate == "kg.mentions" for draft in product.drafts)
    assert len(product.proposals) == 1
    proposal = product.proposals[0]
    assert proposal.reason == "unknown_entity_type"
    assert proposal.count == 2
    assert proposal.samples == raw.relations
    assert proposal.entity_samples == (ExtractedEntity(name="Acme", type="company"),)


def test_unknown_entity_without_relation_still_produces_a_bounded_proposal() -> None:
    """Standalone excluded declarations are counted even when no relationship mentions them."""
    _, source = graph_product()
    unknown = tuple(ExtractedEntity(name=f"Company-{index}", type="company") for index in range(23))
    product = assemble_extraction(RawExtraction(entities=unknown), get_schema(), source)
    assert product.entities == ()
    assert product.drafts == ()
    assert product.proposals[0].count == 23
    assert product.proposals[0].samples == ()
    assert product.proposals[0].entity_samples == unknown[:20]


def test_unknown_endpoint_reason_takes_precedence_over_other_endpoint_ambiguity() -> None:
    """An unsupported declared head cannot be hidden by an undeclared multi-type tail."""
    _, source = graph_product()
    raw = RawExtraction(
        entities=(ExtractedEntity(name="Acme", type="company"),),
        relations=(
            ExtractedRelation(
                head="Acme", relation="owns", tail="Missing", evidence="Acme owns Missing."
            ),
        ),
    )
    proposal = assemble_extraction(raw, get_schema(), source).proposals[0]
    assert proposal.reason == "unknown_entity_type"
    assert proposal.count == 2


def test_permitted_declaration_wins_over_an_unknown_duplicate_name() -> None:
    """An additional unknown label is reported without suppressing an already valid endpoint."""
    expected, source = graph_product()
    raw = pair_result().output
    raw = raw.model_copy(
        update={"entities": (*raw.entities, ExtractedEntity(name="Acme", type="company"))}
    )
    product = assemble_extraction(raw, get_schema(), source)
    assert product.drafts == expected.drafts
    assert product.proposals[0].count == 1
    assert product.proposals[0].samples == ()


def test_unknown_entity_samples_and_counts_survive_worker_merging_and_persistence(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-document reports retain total exclusions while bounding both sample lists."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. Note A.", "Acme uses Widget. Note B."))
    unknown = tuple(ExtractedEntity(name=f"Company-{index}", type="company") for index in range(23))
    raw = RawExtraction(
        entities=unknown,
        relations=(
            ExtractedRelation(head="Company-0", relation="uses", tail="Widget", evidence=""),
        ),
    )
    output = ExtractionResult(output=raw)
    install_adapter(monkeypatch, (output, output))
    run = execute_graph(db, prepare_graph(db, dataset))
    assert run.status == "completed"
    assert len(run.report.proposals) == 1
    proposal = run.report.proposals[0]
    assert proposal.reason == "unknown_entity_type"
    assert proposal.count == 48
    assert len(proposal.samples) == 2
    assert proposal.entity_samples == unknown[:20]
    assert get_job(db, run.id).run.report.proposals == run.report.proposals
