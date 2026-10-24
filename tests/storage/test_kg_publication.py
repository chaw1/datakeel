# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise graph publication through real actions, worker leases and evidence audits."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import JsonDocument
from datakeel.kg.loader import get_profile, get_schema
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_projection import projection_hash, rebuild_evidence
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import list_assertions, validated_bundle
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_context import graph_events
from datakeel.storage.kg_queries import explain_relation, get_source_text, query_kg
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.evidence_models import AssertionStatus
    from datakeel.storage.database import Database


def _review(db: Database, identifier: str, status: AssertionStatus = "accepted") -> None:
    plan = prepare_action(
        db,
        "decide_assertions",
        JsonDocument(root={"assertion_ids": [identifier], "status": status}),
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_identical_reextraction_reuses_facts_and_has_zero_model_calls(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second action uses cached raw output and preserves immutable fact identities."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    adapter = install_adapter(monkeypatch, (pair_result(),))
    first = execute_graph(db, prepare_graph(db, dataset))
    identities = {assertion.id for assertion in list_assertions(db)}
    second = execute_graph(db, prepare_graph(db, dataset))
    assert first.status == second.status == "completed"
    assert adapter.calls == 1
    assert second.report.cached == 1
    assert second.report.model_calls == 0
    assert list_traces(db, second.id) == []
    assert {assertion.id for assertion in list_assertions(db)} == identities
    assert len(list_assertions(db, include_invalidated=True)) == len(identities)
    assert list_decisions(db) == []
    events = graph_events(db)
    assert validated_bundle(events[-1]).prior_cache_event_ids == (events[0].event_id,)


@pytest.mark.parametrize("configuration", ["model", "schema"])
def test_semantic_configuration_change_invalidates_prior_facts_and_cache(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configuration: str
) -> None:
    """A model or schema revision reruns extraction even when text and output are identical."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    adapter = install_adapter(monkeypatch, (pair_result(), pair_result()))
    execute_graph(db, prepare_graph(db, dataset))
    old_ids = {assertion.id for assertion in list_assertions(db)}
    if configuration == "model":
        changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})
        monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: changed)
    else:
        schema = get_schema().model_copy(update={"version": "changed"})
        monkeypatch.setattr("datakeel.storage.kg_preparation.get_schema", lambda _id: schema)
    run = execute_graph(db, prepare_graph(db, dataset))
    current = {assertion.id for assertion in list_assertions(db)}
    assert run.status == "completed"
    assert run.report.cached == 0
    assert adapter.calls == 2
    assert current.isdisjoint(old_ids)
    assert {decision.assertion_id for decision in list_decisions(db)} == old_ids
    assert all(decision.action == "invalidate" for decision in list_decisions(db))
    assert rebuild_evidence(db).matches


def test_configuration_round_trip_reactivates_original_review_and_rebuilds_exactly(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Returning A→B→A restores the original immutable ID and its human accepted status."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    adapter = install_adapter(monkeypatch, (pair_result(), pair_result()))
    profile = get_profile("fake")
    execute_graph(db, prepare_graph(db, dataset))
    original = query_kg(db, KGQuery()).relations[0].assertion
    _review(db, original.id)
    changed = profile.model_copy(update={"model": "fixture-v2"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: changed)
    execute_graph(db, prepare_graph(db, dataset))
    assert original.id not in {assertion.id for assertion in list_assertions(db)}
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: profile)
    restored = execute_graph(db, prepare_graph(db, dataset))
    current = query_kg(db, KGQuery()).relations[0].assertion
    assert current.id == original.id
    assert current.status == "accepted"
    assert current.producer_event_id == original.producer_event_id
    assert (
        original.producer_event_id in validated_bundle(graph_events(db)[-1]).prior_cache_event_ids
    )
    assert restored.report.cached == 1
    assert adapter.calls == 2
    assert [item.action for item in list_decisions(db) if item.assertion_id == original.id] == [
        "accept",
        "invalidate",
        "reactivate",
    ]
    expected_hash = projection_hash(db)
    expected_ids = {assertion.id for assertion in list_assertions(db)}
    with db.session() as session:
        session.execute(delete(AssertionRow))
        session.commit()
    assert rebuild_evidence(db, expected_hash).matches
    assert projection_hash(db) == expected_hash
    assert {assertion.id for assertion in list_assertions(db)} == expected_ids
    assert query_kg(db, KGQuery()).relations[0].assertion.status == "accepted"


def test_replacing_one_document_retains_the_other_documents_union_evidence(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful empty re-extraction of A removes only A from an A+B shared triple."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. Note A.", "Acme uses Widget. Note B."))
    install_adapter(
        monkeypatch, (pair_result(), pair_result(), ExtractionResult(output=RawExtraction()))
    )
    execute_graph(db, prepare_graph(db, dataset))
    original = query_kg(db, KGQuery()).relations[0].assertion
    assert {anchor.asset_ref.asset_id for anchor in original.anchors} == {
        file.id for file in dataset.files
    }
    changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: changed)
    replaced, retained = dataset.files
    run = execute_graph(db, prepare_graph(db, dataset, file_ids=(replaced.id,)))
    assert run.status == "completed"
    current = query_kg(db, KGQuery()).relations[0].assertion
    assert current.id != original.id
    assert {anchor.asset_ref.asset_id for anchor in current.anchors} == {retained.id}
    assert current.verification_detail is not None
    assert {location.source.asset_id for location in current.verification_detail.locations} == {
        retained.id
    }
    assert get_source_text(db, retained.id, dataset.version_id).text.endswith("Note B.")
    assert (
        original.producer_event_id in validated_bundle(graph_events(db)[-1]).prior_cache_event_ids
    )
    assert rebuild_evidence(db).matches


def test_graph_review_freezes_source_anchors_and_preserves_needs_review_content(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Human acceptance changes status but cannot manufacture missing source evidence."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. Note A.", "Acme uses Widget. Note B."))
    install_adapter(monkeypatch, (pair_result(tail="Vivo"), pair_result(tail="Vivo")))
    execute_graph(db, prepare_graph(db, dataset))
    relation = query_kg(db, KGQuery()).relations[0].assertion
    plan = prepare_action(
        db,
        "decide_assertions",
        JsonDocument(root={"assertion_ids": [relation.id], "status": "accepted"}),
    )
    assert {
        (item.asset_ref.asset_id, item.asset_ref.version) for item in plan.manifest.objects
    } == {(file.id, dataset.version_id) for file in dataset.files}
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    accepted = explain_relation(db, relation.id).relation.assertion
    assert accepted.status == "accepted"
    assert accepted.verification == "needs_review"
    assert accepted.anchors == relation.anchors
    assert accepted.verification_detail == relation.verification_detail
    assert rebuild_evidence(db).matches


def test_reviewed_same_as_pair_survives_profile_change_without_new_pair_claim(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configuration refresh cannot discard a human rejection and remerge aliases."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.", "Acme Group uses Widget."))
    outputs = (pair_result(), pair_result("Acme Group"))
    install_adapter(monkeypatch, (*outputs, *outputs))
    execute_graph(db, prepare_graph(db, dataset))
    pair = next(item for item in list_assertions(db) if item.predicate == "kg.same_as")
    _review(db, pair.id, "rejected")
    changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: changed)
    execute_graph(db, prepare_graph(db, dataset))
    pairs = [item for item in list_assertions(db) if item.predicate == "kg.same_as"]
    assert len(pairs) == 1
    assert pairs[0].id == pair.id
    assert pairs[0].status == "rejected"
    assert rebuild_evidence(db).matches


def test_rebuild_preserves_every_mention_and_repeated_sentence_block_anchor(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Canonical bundle replay retains both occurrences after same-triple cross-block merging."""
    sentence = "Acme uses Widget."
    dataset = text_dataset(db, tmp_path, (f"{sentence} {sentence}",))
    profile = get_profile("fake").model_copy(
        update={"chunk_size": len(sentence) + 1, "chunk_overlap": 0}
    )
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: profile)
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    run = execute_graph(db, prepare_graph(db, dataset))
    assert run.report.blocks == 2
    assertions = list_assertions(db)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    assert len([item for item in assertions if item.predicate == "kg.mentions"]) == 4
    assert len(relation.anchors) == 6
    assert relation.verification_detail is not None
    assert {
        location.evidence.start
        for location in relation.verification_detail.locations
        if location.evidence
    } == {0, len(sentence) + 1}
    expected = projection_hash(db)
    assert rebuild_evidence(db, expected).matches
    assert query_kg(db, KGQuery()).relations[0].assertion == relation


def test_same_text_at_a_different_path_reuses_raw_cache_without_mixing_dataset_entities(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Location and dataset identity cannot alter raw content caching or cross graph scopes."""
    first = text_dataset(db, tmp_path / "first", ("Acme uses Widget.",))
    second = text_dataset(db, tmp_path / "second", ("Acme uses Widget.",))
    adapter = install_adapter(monkeypatch, (pair_result(),))
    execute_graph(db, prepare_graph(db, first))
    run = execute_graph(db, prepare_graph(db, second))
    assert run.report.cached == 1
    assert adapter.calls == 1
    left = query_kg(db, KGQuery(dataset_id=first.dataset_id))
    right = query_kg(db, KGQuery(dataset_id=second.dataset_id))
    assert left.version_id == first.version_id
    assert right.version_id == second.version_id
    assert {item.asset_ref.asset_id for item in left.entities}.isdisjoint(
        item.asset_ref.asset_id for item in right.entities
    )


def test_partial_document_refresh_does_not_duplicate_a_retained_candidate_alias_pair(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """New successful blocks cannot duplicate a prior pair carried by an incomplete document."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.", "Acme Group uses Widget. X."))
    install_adapter(
        monkeypatch,
        (
            pair_result(),
            pair_result("Acme Group"),
            pair_result(),
            pair_result("Acme Group"),
            "timeout",
        ),
    )
    execute_graph(db, prepare_graph(db, dataset))
    original = next(item for item in list_assertions(db) if item.predicate == "kg.same_as")
    changed = get_profile("fake").model_copy(
        update={"model": "fixture-v2", "chunk_size": 24, "chunk_overlap": 0}
    )
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: changed)
    refreshed = execute_graph(db, prepare_graph(db, dataset))
    assert refreshed.status == "partial"
    assert refreshed.report.failed == 1
    pairs = [item for item in list_assertions(db) if item.predicate == "kg.same_as"]
    assert len(pairs) == 1
    assert pairs[0].status == "candidate"
    assert pairs[0].extractor == original.extractor
    assert {anchor.asset_ref.asset_id for anchor in pairs[0].anchors} == {dataset.files[1].id}
    assert rebuild_evidence(db).matches
