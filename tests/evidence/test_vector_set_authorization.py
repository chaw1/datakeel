# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""All-reference authorization and stale dynamic closure rejection on generated fixtures."""

from pathlib import Path

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.vector_assertion_rules import assertion_references
from datakeel.core.vector_measurements import CoverageMeasurement
from datakeel.dataset_store.datasets import persist_files
from datakeel.dataset_store.rows import FileStateRow, VersionRow
from datakeel.persistence.task_queries import query_task
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_queries import get_evidence
from datakeel.storage.evidence_store import list_assertions
from datakeel.worker.runner import run_worker
from tests.assets.entry_helpers import grant, publish, revoke
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.vector_helpers import (
    vector_dataset,
    vector_prepare,
    vector_run,
    vector_schedule,
)


def test_gap_non_nearest_reference_authorizes_prepare_read_review_and_revoke(
    db: Database, tmp_path: Path
) -> None:
    """Protecting a non-nearest R member denies every source-bearing entrance."""
    target = vector_dataset(db, tmp_path / "target", (b"target",))
    reference_datasets = [
        vector_dataset(db, tmp_path / f"ref-{i}", (f"ref-{i}".encode(),)) for i in range(3)
    ]
    reference_ids = [source_manifest(db, dataset)[1][0].id for dataset in reference_datasets]
    pipeline = set_pipeline(
        "evidence.coverage_gap",
        {
            "reference": {"filters": [{"field": "id", "operator": "in", "value": reference_ids}]},
            "threshold": 1.0,
        },
    )
    task = vector_run(db, target, pipeline)
    assert task.state == "COMPLETED", task.error
    fact = list_assertions(db)[0]
    assert isinstance(fact.measurement, CoverageMeasurement)
    non_nearest = next(
        m.subject for m in fact.measurement.references if m.subject != fact.measurement.nearest
    )
    assert non_nearest in assertion_references(fact)
    with db.session() as session:
        version = session.get(VersionRow, non_nearest.version)
        assert version
        protected_dataset = version.dataset_id
    policy = publish(db, AssetRef(asset_id=protected_dataset))
    access = AccessContext(actor="local", entry="ask", scope="query")
    with pytest.raises(AuthorizationError):
        vector_prepare(db, target, pipeline)
    with pytest.raises(AuthorizationError):
        get_evidence(db, fact.subject.asset_id, fact.subject.version, access=access)
    with pytest.raises(AuthorizationError):
        prepare_action(
            db,
            "decide_assertions",
            JsonDocument({"assertion_ids": [fact.id], "status": "accepted"}),
        )
    with pytest.raises(AuthorizationError):
        require_access(db, (AssetRef(asset_type="assertion", asset_id=fact.id),), access)
    grant_id = grant(db, policy, "valid", "query")
    assert grant_id
    plan = vector_prepare(db, target, pipeline)
    review = prepare_action(
        db, "decide_assertions", JsonDocument({"assertion_ids": [fact.id], "status": "accepted"})
    )
    assert len(review.manifest.objects) == 4
    queued = vector_schedule(db, plan)
    revoke(db, grant_id)
    run_worker(db, once=True)
    failed = query_task(db, queued)
    assert failed.state == "FAILED"
    assert failed.vector
    assert failed.vector.attempts == ()
    with pytest.raises(AuthorizationError):
        execute_plan(db, review.id, ExecuteRequest(plan_digest=review.plan_digest))


def test_gap_reference_change_invalidates_query_and_review_including_non_nearest(
    db: Database, tmp_path: Path
) -> None:
    """A removed non-nearest R member invalidates every old relative candidate."""
    target = vector_dataset(db, tmp_path / "target", (b"target",))
    reference = vector_dataset(db, tmp_path / "reference", (b"ref-one", b"ref-two"))
    pipeline = set_pipeline(
        "evidence.coverage_gap", {"reference": {"dataset_id": reference}, "threshold": 1.0}
    )
    task = vector_run(db, target, pipeline)
    assert task.state == "COMPLETED", task.error
    fact = list_assertions(db)[0]
    assert isinstance(fact.measurement, CoverageMeasurement)
    other = next(
        m.subject for m in fact.measurement.references if m.subject != fact.measurement.nearest
    )
    with db.session() as session:
        session.add(
            FileStateRow(dataset_id=reference, file_id=other.asset_id, deleted=True, revision=1)
        )
        session.commit()
    assert list_assertions(db) == []
    assert len(list_assertions(db, include_invalidated=True)) == 1
    assert get_evidence(db, fact.subject.asset_id, fact.subject.version).assertions == []
    with pytest.raises(ConflictError, match="read-only audit"):
        prepare_action(
            db,
            "decide_assertions",
            JsonDocument({"assertion_ids": [fact.id], "status": "accepted"}),
        )


def test_cluster_reference_only_review_uses_real_sources(db: Database, tmp_path: Path) -> None:
    """A cluster endpoint is never registered as a public object or reviewed as a file."""
    dataset = vector_dataset(db, tmp_path / "target", (b"same", b"same", b"same"))
    task = vector_run(
        db, dataset, set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    )
    assert task.state == "COMPLETED", task.error
    facts = list_assertions(db)
    assert len(facts) == 3
    review = prepare_action(
        db,
        "decide_assertions",
        JsonDocument({"assertion_ids": [facts[0].id], "status": "accepted"}),
    )
    assert len(review.manifest.objects) == 3
    assert all(o.asset_ref.asset_type == "file" for o in review.manifest.objects)
    result = execute_plan(db, review.id, ExecuteRequest(plan_digest=review.plan_digest))
    assert result.status == "SUCCEEDED"
    assert any(f.status == "accepted" for f in list_assertions(db))


def test_gap_overlap_embeds_union_and_scores_difference(db: Database, tmp_path: Path) -> None:
    """A reference subset of T is sent once and only remaining targets produce candidates."""
    dataset = vector_dataset(db, tmp_path / "target")
    _, files = source_manifest(db, dataset)
    reference = {"dataset_id": dataset, "filters": [{"field": "id", "value": files[0].id}]}
    task = vector_run(
        db,
        dataset,
        set_pipeline(
            "evidence.coverage_gap",
            {"reference": reference, "threshold": 1.0, "max_reference_comparisons": 2},
        ),
    )
    assert task.state == "COMPLETED", task.error
    assert task.vector
    assert len(task.vector.attempts) == 3
    assert {f.subject.asset_id for f in list_assertions(db)} == {f.id for f in files[1:]}


def test_reference_query_revision_change_reembeds_only_changed_peer(
    db: Database, tmp_path: Path
) -> None:
    """Switching R to a new source version invalidates old anchors and reuses unchanged peers."""
    target = vector_dataset(db, tmp_path / "target", (b"target",))
    reference = vector_dataset(db, tmp_path / "references", (b"ref-one", b"ref-two"))
    pipeline = set_pipeline(
        "evidence.coverage_gap", {"reference": {"dataset_id": reference}, "threshold": 1.0}
    )
    first = vector_run(db, target, pipeline)
    assert first.state == "COMPLETED", first.error
    old = list_assertions(db)[0]
    _, files = source_manifest(db, reference)
    changed_path = tmp_path / "changed.txt"
    changed_path.write_bytes(b"new-reference-bytes")
    changed = files[0].model_copy(update={"path": str(changed_path)})
    stored = persist_files([changed, *files[1:]])
    with db.session() as session:
        version = VersionRow(
            dataset_id=reference, manifest=[f.model_dump(mode="json") for f in stored]
        )
        session.add(version)
        session.commit()
        version_id = version.id
    revised = set_pipeline(
        "evidence.coverage_gap",
        {"reference": {"dataset_id": reference, "version_ids": [version_id]}, "threshold": 1.0},
    )
    second = vector_run(db, target, revised)
    assert second.state == "COMPLETED", second.error
    assert second.vector
    assert len(second.vector.attempts) == 1
    current = list_assertions(db)
    assert len(current) == 1
    assert current[0].id != old.id
    assert current[0].measurement != old.measurement
