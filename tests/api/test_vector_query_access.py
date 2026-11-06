# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Whole-run source authorization and dynamic R invalidation before filters or pagination."""

from pathlib import Path

from sqlalchemy import func, select

from datakeel.api.app import create_app
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef
from datakeel.core.vector_measurements import CoverageMeasurement
from datakeel.dataset_store.rows import FileStateRow, VersionRow
from datakeel.storage.data_asset_rows import AssetUsageRow
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_store import list_assertions
from tests.asgi_client import TestClient
from tests.assets.entry_helpers import grant, publish, revoke
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.vector_helpers import vector_dataset, vector_run


def test_vector_query_all_r_authorization_revocation_and_no_side_effects(
    db: Database, tmp_path: Path
) -> None:
    """Non-nearest R denies the entire query, including empty filters and subsequent pages."""
    task_id, fact = _coverage(db, tmp_path)
    assert isinstance(fact.measurement, CoverageMeasurement)
    other = next(
        m.subject for m in fact.measurement.references if m.subject != fact.measurement.nearest
    )
    with db.session() as session:
        version = session.get(VersionRow, other.version)
        assert version
        protected_dataset = version.dataset_id
    policy = publish(db, AssetRef(asset_id=protected_dataset))
    body = {"run_id": task_id, "kind": "coverage", "page_size": 1}
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        assert client.post("/api/evidence/vector/query", json=body).status_code == 403
        assert (
            client.post(
                "/api/evidence/vector/query", json={**body, "subject_ids": ["missing"]}
            ).status_code
            == 403
        )
        grant_id = grant(db, policy, "valid", "query")
        assert grant_id
        with db.session() as session:
            before = session.scalar(select(func.count()).select_from(AssetUsageRow))
        first = client.post("/api/evidence/vector/query", json=body)
        assert first.status_code == 200, first.text
        data = first.json()
        assert data["total"] == 2
        assert data["items"][0]["measurement"]["reference_digest"]
        assert len(data["items"][0]["measurement"]["references"]) == 3
        filtered = client.post(
            "/api/evidence/vector/query", json={**body, "reference_id": other.asset_id}
        )
        assert filtered.json()["total"] == 2
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(AssetUsageRow)) == before
        revoke(db, grant_id)
        assert (
            client.post(
                "/api/evidence/vector/query", json={**body, "cursor": data["next_cursor"]}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/evidence/assertions/decide",
                json={
                    "assertion_ids": [fact.id],
                    "status": "accepted",
                },
            ).status_code
            == 403
        )


def test_vector_query_changed_r_invalidates_cursor_and_retains_history(
    db: Database, tmp_path: Path
) -> None:
    """A non-nearest member change invalidates the result without erasing old facts."""
    target = vector_dataset(db, tmp_path / "target", (b"target", b"other"))
    refs = vector_dataset(db, tmp_path / "refs", (b"ref-a", b"ref-b"))
    task = vector_run(
        db,
        target,
        set_pipeline(
            "evidence.coverage_gap",
            {
                "reference": {"dataset_id": refs},
                "threshold": 1.0,
            },
        ),
    )
    fact = list_assertions(db)[0]
    assert isinstance(fact.measurement, CoverageMeasurement)
    other = next(
        m.subject for m in fact.measurement.references if m.subject != fact.measurement.nearest
    )
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        body = {"run_id": task.id, "kind": "coverage", "page_size": 1}
        first = client.post("/api/evidence/vector/query", json=body).json()
        with db.session() as session:
            session.add(
                FileStateRow(dataset_id=refs, file_id=other.asset_id, deleted=True, revision=1)
            )
            session.commit()
        assert (
            client.post(
                "/api/evidence/vector/query", json={**body, "cursor": first["next_cursor"]}
            ).status_code
            == 422
        )
        current = client.post("/api/evidence/vector/query", json=body).json()
        assert current["status"] == "stale"
        assert current["reason"] == "vector_results_stale"
        assert current["items"] == []
        assert len(list_assertions(db, include_invalidated=True)) == 2


def test_vector_query_zero_candidates_still_validates_full_reference_scope(
    db: Database, tmp_path: Path
) -> None:
    """An empty successful gap result becomes explicitly stale when R changes."""
    target = vector_dataset(db, tmp_path / "target", (b"same",))
    refs = vector_dataset(db, tmp_path / "refs", (b"same", b"same"))
    task = vector_run(
        db,
        target,
        set_pipeline(
            "evidence.coverage_gap",
            {
                "reference": {"dataset_id": refs},
                "threshold": -1.0,
            },
        ),
    )
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        body = {"run_id": task.id, "kind": "coverage"}
        result = client.post("/api/evidence/vector/query", json=body).json()
        assert result["status"] == "current"
        assert result["total"] == 0
        _, files = source_manifest(db, refs)
        with db.session() as session:
            session.add(
                FileStateRow(dataset_id=refs, file_id=files[0].id, deleted=True, revision=1)
            )
            session.commit()
        changed = client.post("/api/evidence/vector/query", json=body).json()
        assert changed["status"] == "stale"
        assert changed["snapshot"] != result["snapshot"]


def test_vector_query_protects_duplicate_neighbor_and_non_subject_cluster_member(
    db: Database, tmp_path: Path
) -> None:
    """Filtering to a visible subject never bypasses any disclosed peer's protection."""
    dataset = vector_dataset(db, tmp_path, (b"same",) * 3)
    duplicate = vector_run(db, dataset)
    cluster = vector_run(
        db, dataset, set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    )
    _, files = source_manifest(db, dataset)
    publish(db, AssetRef(asset_id=dataset))
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        for task, kind in ((duplicate, "duplicate"), (cluster, "cluster")):
            assert (
                client.post(
                    "/api/evidence/vector/query",
                    json={
                        "run_id": task.id,
                        "kind": kind,
                        "subject_ids": [files[0].id],
                    },
                ).status_code
                == 403
            )


def _coverage(db: Database, tmp_path: Path) -> tuple[str, Assertion]:
    target = vector_dataset(db, tmp_path / "target", (b"target", b"other"))
    datasets = [vector_dataset(db, tmp_path / f"ref-{i}", (f"ref-{i}".encode(),)) for i in range(3)]
    ids = [source_manifest(db, dataset)[1][0].id for dataset in datasets]
    task = vector_run(
        db,
        target,
        set_pipeline(
            "evidence.coverage_gap",
            {
                "reference": {"filters": [{"field": "id", "operator": "in", "value": ids}]},
                "threshold": 1.0,
            },
        ),
    )
    return task.id, list_assertions(db)[0]
