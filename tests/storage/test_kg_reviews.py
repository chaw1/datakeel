# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve human conclusions when graph evidence and extraction identities change."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import JsonDocument
from datakeel.kg.loader import get_profile
from datakeel.storage.database import VersionRow
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.kg_queries import explain_relation, graph_kg, query_kg
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


def _review(db: Database, identifiers: list[str], status: AssertionStatus) -> None:
    plan = prepare_action(
        db,
        "decide_assertions",
        JsonDocument.model_validate({"assertion_ids": identifiers, "status": status}),
    )
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert result.status == "SUCCEEDED"


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_new_file_inherits_review_and_exposes_all_original_evidence(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: AssertionStatus
) -> None:
    """A later source extends reviewed triples and mentions without reopening the review."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. Note A.", "Acme uses Widget. Note B."))
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    first, second = dataset.files
    execute_graph(db, prepare_graph(db, dataset, file_ids=(first.id,)))
    original = query_kg(db, KGQuery()).relations[0].assertion
    _review(db, [item.id for item in list_assertions(db)], status)
    execute_graph(db, prepare_graph(db, dataset, file_ids=(second.id,)))
    current = query_kg(db, KGQuery()).relations[0].assertion
    assert current.id != original.id
    assert {item.status for item in list_assertions(db)} == {status}
    assert {anchor.asset_ref.asset_id for anchor in current.anchors} == {first.id, second.id}
    assert len([item for item in list_assertions(db) if item.predicate == "kg.mentions"]) == 4
    explanation = explain_relation(db, current.id)
    assert {source.text for source in explanation.sources} == {
        "Acme uses Widget. Note A.",
        "Acme uses Widget. Note B.",
    }
    inherited = list_decisions(db, current.id)
    assert len(inherited) == 1
    assert f"source_assertion_id={original.id}" in inherited[0].reason
    assert "source_decision_id=" in inherited[0].reason
    assert inherited[0].producer_event_id == current.producer_event_id
    expected = list_assertions(db)
    assert rebuild_evidence(db).matches
    assert list_assertions(db) == expected
    assert list_decisions(db, current.id) == inherited


@pytest.mark.parametrize("status", ["accepted", "rejected"])
@pytest.mark.parametrize("changed_profile", [False, True])
def test_review_survives_same_file_reextraction_with_cached_or_changed_configuration(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: AssertionStatus,
    *,
    changed_profile: bool,
) -> None:
    """Both reused assertions and new configuration identities keep each human conclusion."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    adapter = install_adapter(monkeypatch, (pair_result(), pair_result()))
    execute_graph(db, prepare_graph(db, dataset))
    originals = {item.id for item in list_assertions(db)}
    _review(db, sorted(originals), status)
    if changed_profile:
        changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})
        monkeypatch.setattr(
            "datakeel.storage.kg_preparation.get_profile", lambda _id="fake": changed
        )
    run = execute_graph(db, prepare_graph(db, dataset))
    current = list_assertions(db)
    assert {item.status for item in current} == {status}
    assert adapter.calls == (2 if changed_profile else 1)
    assert run.report.cached == (0 if changed_profile else 1)
    assert {item.id for item in current}.isdisjoint(originals) == changed_profile
    assert rebuild_evidence(db).matches


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_reviewed_triple_disappears_only_when_last_supporting_source_is_replaced(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: AssertionStatus
) -> None:
    """Removing A keeps B and its review; removing B then invalidates the remaining facts."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. Note A.", "Acme uses Widget. Note B."))
    empty = ExtractionResult(output=RawExtraction())
    install_adapter(monkeypatch, (pair_result(), pair_result(), empty, empty))
    execute_graph(db, prepare_graph(db, dataset))
    _review(db, [item.id for item in list_assertions(db)], status)
    changed = get_profile("fake").model_copy(update={"model": "fixture-v2"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id="fake": changed)
    first, second = dataset.files
    execute_graph(db, prepare_graph(db, dataset, file_ids=(first.id,)))
    retained = query_kg(db, KGQuery()).relations[0].assertion
    assert retained.status == status
    assert {anchor.asset_ref.asset_id for anchor in retained.anchors} == {second.id}
    execute_graph(db, prepare_graph(db, dataset, file_ids=(second.id,)))
    assert list_assertions(db) == []
    assert list_decisions(db, retained.id)[-1].action == "invalidate"
    assert list_decisions(db, retained.id)[-1].status == status
    assert rebuild_evidence(db).matches
    assert list_assertions(db) == []


@pytest.mark.parametrize("latest_status", ["rejected", "candidate"])
def test_latest_direct_review_overrides_old_configuration_and_inherited_audits(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    latest_status: AssertionStatus,
) -> None:
    """A new explicit rejection or restore remains authoritative on a configuration roundtrip."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    install_adapter(monkeypatch, (pair_result(), pair_result()))
    profile = get_profile("fake")
    execute_graph(db, prepare_graph(db, dataset))
    original = query_kg(db, KGQuery()).relations[0].assertion
    _review(db, [original.id], "accepted")
    changed = profile.model_copy(update={"model": "fixture-v2"})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id="fake": changed)
    execute_graph(db, prepare_graph(db, dataset))
    newer = query_kg(db, KGQuery()).relations[0].assertion
    assert newer.status == "accepted"
    _review(db, [newer.id], latest_status)
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id="fake": profile)
    execute_graph(db, prepare_graph(db, dataset))
    current = query_kg(db, KGQuery()).relations[0].assertion
    assert current.id == original.id
    assert current.status == latest_status
    assert f"source_assertion_id={newer.id}" in list_decisions(db, original.id)[-1].reason
    assert rebuild_evidence(db).matches


@pytest.mark.parametrize("scope", ["dataset", "version"])
def test_review_inheritance_is_isolated_to_its_dataset_version(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    """Identical source content in another graph scope never acquires an unrelated review."""
    dataset = text_dataset(db, tmp_path / "first", ("Acme uses Widget.",))
    install_adapter(monkeypatch, (pair_result(),))
    execute_graph(db, prepare_graph(db, dataset))
    _review(db, [item.id for item in list_assertions(db)], "accepted")
    if scope == "dataset":
        other = text_dataset(db, tmp_path / "other", ("Acme uses Widget.",))
    else:
        with db.session() as session:
            version = VersionRow(
                dataset_id=dataset.dataset_id,
                manifest=[item.model_dump(mode="json") for item in dataset.files],
            )
            session.add(version)
            session.flush()
            other = dataset.model_copy(update={"version_id": version.id})
            session.commit()
    execute_graph(db, prepare_graph(db, other))
    graph = query_kg(db, KGQuery(dataset_id=other.dataset_id, version_id=other.version_id))
    assert graph.relations[0].assertion.status == "candidate"
    assert all(
        mention.status == "candidate" for entity in graph.entities for mention in entity.mentions
    )
    assert rebuild_evidence(db).matches


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_reviewed_alias_gains_new_source_without_reopening_review_or_merging_rejection(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: AssertionStatus
) -> None:
    """A third file extends a reviewed pair's drawer and audit while preserving display policy."""
    dataset = text_dataset(
        db,
        tmp_path,
        ("Acme uses Widget. A.", "Acme Group uses Widget. B.", "Acme Group uses Widget. C."),
    )
    install_adapter(
        monkeypatch, (pair_result(), pair_result("Acme Group"), pair_result("Acme Group"))
    )
    first, second, third = dataset.files
    execute_graph(db, prepare_graph(db, dataset, file_ids=(first.id, second.id)))
    original = next(item for item in list_assertions(db) if item.predicate == "kg.same_as")
    _review(db, [original.id], status)
    execute_graph(db, prepare_graph(db, dataset, file_ids=(third.id,)))
    pairs = [item for item in list_assertions(db) if item.predicate == "kg.same_as"]
    assert len(pairs) == 1
    current = pairs[0]
    assert current.id != original.id
    assert current.status == status
    assert {anchor.asset_ref.asset_id for anchor in current.anchors} == {
        first.id,
        second.id,
        third.id,
    }
    assert current.verification_detail is not None
    assert {location.source.asset_id for location in current.verification_detail.locations} == {
        first.id,
        second.id,
        third.id,
    }
    assert len(explain_relation(db, current.id).sources) == 3
    assert f"source_assertion_id={original.id}" in list_decisions(db, current.id)[0].reason
    graph = graph_kg(db, KGQuery())
    organizations = [node for node in graph.nodes if node.entity_type == "organization"]
    assert len(organizations) == (1 if status == "accepted" else 2)
    assert rebuild_evidence(db).matches
    assert graph_kg(db, KGQuery()) == graph
