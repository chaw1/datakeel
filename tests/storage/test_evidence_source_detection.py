# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence-backed object quality depends on selected manifests, not editable dataset labels."""

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.models import ObjectSet, PropertyFilter
from datakeel.storage import object_queries
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_queries import query_evidence
from datakeel.storage.evidence_snapshot import EvidenceSnapshot
from datakeel.storage.governance_service import MetadataInput, save_metadata
from datakeel.storage.object_queries import evaluate
from tests.evidence.interface_fixtures import seed_query_evidence


def test_selection_when_user_metadata_replaced_keeps_query_and_action_quality(
    db: Database, tmp_path: Path
) -> None:
    """Retain measured corrupt quality after metadata replacement and in exact-ID actions."""
    dataset_id = seed_query_evidence(db, tmp_path / "samples")
    query = EvidenceQuery(dataset_id=dataset_id, quality_max=0)
    before = query_evidence(db, query)
    assert before.total == 1
    saved = save_metadata(
        db, dataset_id, MetadataInput(values={"owner": "local"}, reason="Update owner")
    )
    assert saved.values == {"owner": "local"}
    assert query_evidence(db, query) == before
    frozen = evaluate(db, query.selection())
    sample = before.items[0]
    assert [item.asset_ref for item in frozen.objects] == [sample.asset_ref]
    assert frozen.objects[0].properties["quality"] == sample.quality_score == 0
    exact = ObjectSet(
        dataset_id=dataset_id,
        version_ids=[sample.source_version],
        filters=[PropertyFilter(field="id", value=sample.asset_ref.asset_id)],
    )
    plan = prepare_action(
        db,
        "quarantine_files",
        JsonDocument({"selection": exact.model_dump(mode="json")}),
    )
    assert plan.manifest.objects[0].properties["quality"] == sample.quality_score
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    assert execute_plan(db, plan.id, request).status == "SUCCEEDED"


def test_selection_when_legacy_source_has_no_evidence_does_not_load_snapshot(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Avoid scanning assertion/cache tables for an ordinary legacy file selection."""
    path = tmp_path / "legacy.txt"
    path.write_text("local generated legacy sample", encoding="utf-8")
    dataset = import_paths(db, "legacy", [path])

    def forbidden_snapshot(
        _session: Session, *, include_peer_splits: bool = False
    ) -> EvidenceSnapshot:
        del include_peer_splits
        msg = "Legacy queries must not read evidence projections"
        raise AssertionError(msg)

    monkeypatch.setattr(object_queries, "read_snapshot", forbidden_snapshot)
    assert len(evaluate(db, ObjectSet(dataset_id=dataset.id)).objects) == 1


def test_selection_when_dataset_file_cache_differs_uses_immutable_source_manifest(
    db: Database, tmp_path: Path
) -> None:
    """Find evidence in the requested historical version independently of mutable row fields."""
    dataset_id = seed_query_evidence(db, tmp_path / "samples")
    query = EvidenceQuery(dataset_id=dataset_id, quality_max=0)
    sample = query_evidence(db, query).items[0]
    with db.session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        source = session.get(VersionRow, sample.source_version)
        assert dataset is not None
        assert source is not None
        dataset.metadata_values = {}
        dataset.files = []
        session.commit()
    selected = evaluate(db, query.selection().model_copy(update={"version_ids": [source.id]}))
    assert [item.asset_ref for item in selected.objects] == [sample.asset_ref]
    assert selected.objects[0].properties["quality"] == sample.quality_score
